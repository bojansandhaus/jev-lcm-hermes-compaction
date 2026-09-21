"""Operator diagnostics and a bounded, explicitly requested live probe."""
import argparse
import json
import time
from dataclasses import replace
from .settings import Settings
from .providers import ProviderChain
from .jev_client import ProviderError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("jev_providers", "jev_calibrate"))
    parser.add_argument(chr(45) * 2 + "dry-run", action="store_true")
    parser.add_argument(chr(45) * 2 + "conservative", action="store_true")
    args = parser.parse_args()
    settings = replace(Settings(), conservative=args.conservative)
    chain = ProviderChain(settings)
    result = chain.diagnostics()
    if args.command == "jev_calibrate":
        if not args.dry_run:
            parser.error("live calibration requires the dry-run flag; runtime calibration uses session scores")
        start = time.monotonic()
        try:
            result['scores'] = chain.score({'synthetic': 'Retain identifier abc123def456 for the next step.'}, {'probe': {'type': 'noul', 'instructions': 'Is the identifier needed verbatim?'}})
            result['status'] = 'ok'
        except ProviderError as error:
            result['status'] = error.reason
        result['latency_ms'] = (time.monotonic() - start) * 1000
        result['providers'] = chain.diagnostics()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
