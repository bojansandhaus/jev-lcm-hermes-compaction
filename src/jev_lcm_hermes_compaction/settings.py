"""Validated public configuration. Secrets are supplied separately."""

from dataclasses import dataclass
from urllib.parse import urlsplit, unquote

# The named arrangements, in this package's vocabulary. Each entry in
# ``PROVIDER_MODES`` is canonical and keeps its own chain. ``PROVIDER_ALIASES``
# carries the alternative names for the same three arrangements, so an operator
# can write the mode they mean and get the chain they expect.
PROVIDER_MODES: tuple[str, ...] = (
    "auto",
    "typesafe",
    "openrouter",
    "laya",
    "laya_then_hosted",
)
PROVIDER_ALIASES: dict[str, str] = {
    "jev_api": "auto",
    "laya_local": "laya",
    "laya_with_jev_fallback": "laya_then_hosted",
}


def canonical_provider(value: object) -> str | None:
    """Resolve an accepted provider value, or ``None`` when it is not one.

    An alias resolves to the canonical mode whose behaviour it names, so the
    alias selects the same chain, the same privacy boundary, and the same
    breaker as that mode.
    """
    if not isinstance(value, str):
        return None
    if value in PROVIDER_MODES:
        return value
    return PROVIDER_ALIASES.get(value)


def invalid_provider(value: object) -> ValueError:
    """An error that names every accepted value without echoing secrets."""
    accepted = ", ".join(PROVIDER_MODES)
    aliases = ", ".join(
        alias + " for " + mode for alias, mode in PROVIDER_ALIASES.items()
    )
    return ValueError(
        "invalid jev_provider "
        + repr(value)
        + "; expected one of "
        + accepted
        + ", or the mode alias "
        + aliases
    )


@dataclass(frozen=True)
class Settings:
    jev_provider: str = "auto"
    typesafe_base_url: str = "https://api.typesafe.ai/v1"
    openrouter_base_url: str = "https://openrouter.ai/api"
    openrouter_endpoint_path: str = "/alpha/decisions"
    jev_endpoint_path: str = "/systemone"
    jev_model: str = "jev-latest"
    openrouter_model: str = "~typesafe/jev-latest"
    laya_base_url: str = "http://127.0.0.1:8000"
    laya_endpoint_path: str = "/v1/systemone"
    laya_model: str = "convaiinnovations/laya"
    jev_fallback_enabled: bool = True
    jev_fallback_order: tuple[str, ...] = ("typesafe", "openrouter")
    jev_fallback_on: tuple[str, ...] = (
        "transport_error",
        "timeout",
        "401",
        "403",
        "429",
        "5xx",
    )
    jev_fallback_cooldown_s: float = 60
    jev_fallback_max_retries: int = 1
    request_timeout_s: float = 30
    keep_threshold: float = 0.15
    keep_threshold_max: float = 0.40
    min_keep_rate: float = 0.10
    jev_calibration_enabled: bool = True
    jev_calibration_window: int = 500
    jev_calibration_min_samples: int = 50
    conservative: bool = False
    jev_anchor_protection_enabled: bool = True
    jev_anchor_patterns: tuple[str, ...] = (
        r"\b[a-f0-9]{7,40}\b",
        r"\b[A-Z_]{2,}_(?:KEY|TOKEN|SECRET|URL|PATH|ID)\b",
        r"[^.!?\n]*(?:root cause|because|constraint|must|never|always)[^.!?\n]*[.!?]?",
        r"(?:\bline \d+\b|:[0-9]+:[0-9]+)",
        r"`[^`\n]+`",
        r"[\"'][^\"'\n]*(?:/|\\)[^\"'\n]*[\"']",
        r"\b[vV]?\d+\.\d+\.\d+(?:[+.-][\w.]+)?\b",
    )
    jev_batch_window_turns: int = 3
    jev_max_candidates_per_batch: int = 300
    jev_urgent_context_ratio: float = 0.90
    max_state_tokens: int = 25000
    max_request_tokens: int = 30000
    truncate_head_chars: int = 300
    min_result_chars: int = 8000
    hint_budget_tokens: int = 4000

    def __post_init__(self) -> None:
        mode = canonical_provider(self.jev_provider)
        if mode is None:
            raise invalid_provider(self.jev_provider)
        if mode != self.jev_provider:
            # An alias selects the canonical mode, so every consumer reads one
            # spelling of the arrangement.
            object.__setattr__(self, "jev_provider", mode)
        if (
            not self.jev_fallback_order
            or len(set(self.jev_fallback_order)) != len(self.jev_fallback_order)
            or any(p not in ("typesafe", "openrouter") for p in self.jev_fallback_order)
        ):
            raise ValueError("invalid jev_fallback_order")
        for value in (
            self.keep_threshold,
            self.keep_threshold_max,
            self.min_keep_rate,
            self.jev_urgent_context_ratio,
        ):
            if not 0 <= value <= 1:
                raise ValueError("probability outside [0, 1]")
        for value in (
            self.jev_batch_window_turns,
            self.jev_max_candidates_per_batch,
            self.max_state_tokens,
            self.max_request_tokens,
            self.hint_budget_tokens,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("budgets must be positive integers")
        if self.max_request_tokens <= self.max_state_tokens:
            raise ValueError("request budget must exceed state budget")
        if (
            self.request_timeout_s <= 0
            or self.jev_fallback_cooldown_s < 0
            or self.jev_fallback_max_retries < 0
            or self.min_result_chars < 0
            or self.truncate_head_chars < 0
        ):
            raise ValueError("invalid timeout or size")
        if not 1 <= self.jev_calibration_min_samples <= self.jev_calibration_window:
            raise ValueError("invalid calibration window")
        endpoint(self.typesafe_base_url, self.jev_endpoint_path)
        endpoint(self.openrouter_base_url, self.openrouter_endpoint_path)
        endpoint(self.laya_base_url, self.laya_endpoint_path)


def endpoint(base: str, path: str) -> str:
    decoded = unquote(base + path)
    parsed = urlsplit(base)
    if (
        "\\" in decoded
        or any(ord(c) < 33 for c in decoded)
        or parsed.scheme not in ("https", "http")
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid provider endpoint")
    if not path.startswith("/") or "?" in path or "#" in path or ".." in unquote(path):
        raise ValueError("invalid provider path")
    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError("nonlocal provider requires HTTPS")
    return base.rstrip("/") + path
