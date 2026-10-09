"""Operator diagnostics and a bounded, explicitly requested live probe."""

import argparse
import json
import sys
import time
from dataclasses import replace
from .settings import Settings
from .providers import ProviderChain
from .jev_client import ProviderError


def _build_chain(conservative: bool) -> tuple[ProviderChain | None, str]:
    """Build the routing chain, reporting a load-time failure as data.

    `ProviderChain` rejects a mode that promises a fallback with no key for the
    other side, and `Settings` rejects an unsafe endpoint. Both raise
    `ValueError`, and the value is the operator-facing message. Building it
    outside a guarded path turned that message into a traceback before any
    command could run, which is the one shape an operator cannot act on.
    """
    try:
        settings = replace(Settings(), conservative=conservative)
    except ValueError as error:
        return None, str(error)
    try:
        return ProviderChain(settings), ""
    except ValueError as error:
        return None, str(error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("jev_providers", "jev_calibrate"),
        help="jev_providers prints routing diagnostics; jev_calibrate resolves the same chain",
    )
    parser.add_argument(
        chr(45) * 2 + "dry-run",
        action="store_true",
        help=(
            "do not send anything: report the resolved provider order, which "
            "variables are present, and the cooldown state. Required to run "
            "jev_calibrate at all; without it the command exits"
        ),
    )
    parser.add_argument(
        chr(45) * 2 + "live",
        action="store_true",
        help=(
            "send one real scoring request to the first provider that is not in "
            "cooldown, carrying a synthetic state and one noul question. It "
            "bills that provider on every invocation and it is the only path "
            "here that leaves the machine; --dry-run alone sends nothing"
        ),
    )
    parser.add_argument(
        chr(45) * 2 + "conservative",
        action="store_true",
        help="report the chain as the conservative profile builds it",
    )
    args = parser.parse_args()
    chain, failure = _build_chain(args.conservative)
    if chain is None:
        print(json.dumps({"error": failure, "command": args.command}, indent=2))
        raise SystemExit(2)
    result = chain.diagnostics()
    if args.command == "jev_calibrate":
        if not args.dry_run:
            parser.error(
                "jev_calibrate requires the dry-run flag; runtime calibration uses session scores. "
                "Add --live as well to send one real request"
            )
        if args.live:
            start = time.monotonic()
            try:
                result["scores"] = chain.score(
                    {"synthetic": "Retain identifier abc123def456 for the next step."},
                    {
                        "probe": {
                            "type": "noul",
                            "instructions": "Is the identifier needed verbatim?",
                        }
                    },
                )
                result["status"] = "ok"
            except ProviderError as error:
                result["status"] = error.reason
            result["latency_ms"] = (time.monotonic() - start) * 1000
            result["providers"] = chain.diagnostics()
        else:
            # A dry run resolves the chain and sends nothing. The one request a
            # dry run used to make was billed to the operator's account and the
            # state it carried never reached the model, so the reporting is
            # derived from configuration instead.
            result["status"] = "resolved" if chain.order else "disabled"
            result["sent"] = False
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
