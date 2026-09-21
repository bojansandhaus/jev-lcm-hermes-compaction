"""Runtime Python oracle for the cross-language parity fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jev_lcm_hermes_compaction.calibration import JevThresholdCalibrator
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction.jev_client import ProviderError


def _calibration(case: dict[str, Any]) -> dict[str, Any]:
    cfg = case.get("config", {})
    c = JevThresholdCalibrator(
        minimum=cfg.get("jev_calibration_min_samples", 50),
        window=cfg.get("jev_calibration_window", 500),
        fallback=cfg.get("fallback", 0.15),
        cap=cfg.get("cap", 0.40),
        keep_rate=cfg.get("keep_rate", 0.10),
        conservative=cfg.get("conservative", False),
    )
    return {
        "name": case["name"],
        "threshold": c.observe(case["values"]),
        "calibrated": c.calibrated,
    }


def _provider(case: dict[str, Any]) -> dict[str, Any]:
    kwargs = {"jev_provider": case.get("provider", "auto")}
    chain: ProviderChain | None = None
    now = [0.0]
    responses = {k: list(v) for k, v in case.get("responses", {}).items()}
    seen: list[str] = []

    def transport(url: str, key: str, payload: dict[str, Any], timeout: float) -> Any:
        del key, payload, timeout
        provider = "typesafe" if "typesafe" in url else "openrouter"
        seen.append(provider)
        item = responses[provider].pop(0)
        if "error" in item:
            raise ProviderError(item["error"])
        return item

    result: dict[str, Any] = {"name": case["name"]}
    try:
        chain = ProviderChain(
            Settings(**kwargs), case.get("env", {}), transport, lambda: now[0]
        )
    except (ProviderError, ValueError) as error:
        result.update(
            {
                "constructor_error": str(error),
                "calls": [],
                "seen": [],
                "fallback_count": 0,
                "total_calls": 0,
                "last_provider": "",
            }
        )
        return result
    calls: list[dict[str, Any]] = []
    for advance in (0.0, float(case.get("second_call_after", 0.0))):
        if advance:
            now[0] = advance
        try:
            scores = chain.score({}, {"x": {"type": "noul", "instructions": "fixture"}})
            calls.append({"scores": scores})
        except ProviderError as error:
            calls.append({"error": error.reason})
        if not case.get("second_call_after"):
            break
    result.update(
        {
            "calls": calls,
            "seen": seen,
            "fallback_count": chain.fallback_count,
            "total_calls": chain.calls,
            "last_provider": chain.last_provider,
        }
    )
    return result


def run(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text())
    return {
        "calibration": [_calibration(c) for c in fixture["calibration"]],
        "providers": [_provider(c) for c in fixture["providers"]],
    }


if __name__ == "__main__":
    print(
        json.dumps(
            run(Path(__file__).parent / "fixtures" / "parity_scenarios.json"),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
