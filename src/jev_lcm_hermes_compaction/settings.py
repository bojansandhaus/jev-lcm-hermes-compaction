"""Validated public configuration. Secrets are supplied separately."""

from dataclasses import dataclass
from urllib.parse import urlsplit, unquote

# The four canonical arrangements. Each names which side leads and whether the
# other side is a fallback, so the mode alone says what leaves the machine.
# ``PROVIDER_ALIASES`` carries every previously accepted name, so a deployed
# configuration keeps the routing decision it had before this vocabulary
# existed, and ``PROVIDER_PINS`` carries the ones that also name a hosted
# provider to pin.
PROVIDER_MODES: tuple[str, ...] = (
    "api_with_local_fallback",
    "api_only",
    "local_only",
    "local_with_api_fallback",
)
# Names this package already accepted, mapped to the canonical mode they
# denote. ``auto`` keeps this repository's existing meaning rather than the
# generic one: it resolves the hosted side by credential from
# ``jev_fallback_order`` and never selects the local route on its own
# initiative, so a default profile keeps its current behaviour.
PROVIDER_ALIASES: dict[str, str] = {
    "auto": "api_only",
    "jev_api": "api_only",
    "laya": "local_only",
    "laya_local": "local_only",
    "laya_then_hosted": "local_with_api_fallback",
    "laya_with_jev_fallback": "local_with_api_fallback",
}
# Aliases that additionally pin which hosted provider leads. Each value is
# ``(canonical mode, hosted provider)``. ``typesafe``, ``openrouter``, and
# ``clef`` were already single-provider pins with no fallback hop, so they are
# ``api_only`` with their pin intact rather than a mode that adds one.
PROVIDER_PINS: dict[str, tuple[str, str]] = {
    "typesafe": ("api_only", "typesafe"),
    "openrouter": ("api_only", "openrouter"),
    "clef": ("api_only", "clef"),
    "clef_api": ("api_only", "clef"),
    "clef_with_local_fallback": ("api_with_local_fallback", "clef"),
}
# The Clef checkpoints Cloudflare publishes. This is a checkpoint of one
# provider rather than a provider of its own, so it is a model setting and
# never a chain member.
CLEF_MODELS: tuple[str, ...] = ("clef", "clef-flash")
# The hosted providers a mode may pin or fall back to. The local provider is
# absent by design: it is not a chain member, it only leads or backs a mode.
HOSTED_PROVIDERS: tuple[str, ...] = ("typesafe", "openrouter", "clef")


def resolve_mode(value: object) -> tuple[str, str] | None:
    """Resolve an accepted mode value to ``(canonical mode, pinned provider)``.

    An alias resolves to the canonical mode whose behaviour it names, so the
    alias selects the same chain, the same privacy boundary, and the same
    breaker as that mode. The pin is empty unless the name also named a hosted
    provider, which is how ``typesafe`` stays a TypeSafe pin rather than
    becoming an order resolved from ``jev_fallback_order``.
    """
    if not isinstance(value, str):
        return None
    if value in PROVIDER_MODES:
        return value, ""
    pinned = PROVIDER_PINS.get(value)
    if pinned is not None:
        return pinned
    mode = PROVIDER_ALIASES.get(value)
    return None if mode is None else (mode, "")


def canonical_provider(value: object) -> str | None:
    """The canonical mode a value names, or ``None`` when it names none."""
    resolved = resolve_mode(value)
    return None if resolved is None else resolved[0]


def invalid_provider(value: object) -> ValueError:
    """An error that names every accepted value without echoing secrets."""
    accepted = ", ".join(PROVIDER_MODES)
    aliases = ", ".join(
        alias + " for " + mode for alias, mode in PROVIDER_ALIASES.items()
    )
    pinned = ", ".join(
        alias + " for " + mode + " on " + provider
        for alias, (mode, provider) in PROVIDER_PINS.items()
    )
    return ValueError(
        "invalid jev_provider "
        + repr(value)
        + "; expected one of "
        + accepted
        + ", or the mode alias "
        + aliases
        + ", or the pinned alias "
        + pinned
    )


# The default engine for the local slot. It is the shipped default, not a
# constraint: any other engine name is accepted by ``local_model``.
LOCAL_MODEL_DEFAULT = "laya"
# Characters refused in ``local_model``. The value is sent as the ``model``
# field of a JSON body, and a self-hosted engine may also interpolate it into a
# URL path, so the refused set is the union of what would break either: control
# characters and space, the two JSON string terminators, and the URL delimiters.
_LOCAL_MODEL_FORBIDDEN = '"\\?#'


class Unset(str):
    """Marks a setting left at its default so an explicit value can win.

    ``local_model`` and ``laya_model`` both name the local engine. The dataclass
    has to tell "left alone" from "explicitly asked for", because the
    backwards-compatible rule is that ``local_model`` wins only when it was set
    on purpose. A plain ``None`` would read as an explicit request to unset, and
    a plain default string could not be distinguished from a typed one.

    It is a ``str`` subclass so the field keeps an honest ``str`` annotation for
    every reader, and it is resolved away in ``__post_init__`` before any caller
    can observe the empty value it carries.
    """

    def __repr__(self) -> str:
        return "<unset>"


def resolve_local_model(local_model: str, laya_model: str) -> str:
    """The engine name the local slot sends, and the validation it passes.

    The local slot is interchangeable on purpose, so there is no allowlist:
    a new local model has to work by configuration alone. What is refused is
    only what could not be carried safely, namely an empty or whitespace-only
    name and the characters that would corrupt the JSON ``model`` string or a
    URL path segment built from it.

    ``local_model`` wins when it was set on purpose. Otherwise the
    backwards-compatible ``laya_model`` decides, and when that is left alone
    the shipped default applies, so every existing configuration resolves to
    exactly what it resolved to before this setting existed.

    Both parameters are typed ``str`` because ``Unset`` is a ``str`` subclass:
    "left alone" is carried by the value, not by the annotation. A caller that
    passes something which is not a string at all is rejected by the
    ``isinstance`` check below rather than by a type error at the boundary.
    """
    if isinstance(local_model, Unset):
        # Left alone, so the backwards-compatible setting decides, and a
        # ``laya_model`` that was itself left alone falls through to the
        # documented default of this slot.
        chosen: str = (
            LOCAL_MODEL_DEFAULT if isinstance(laya_model, Unset) else laya_model
        )
    else:
        chosen = local_model
    if not isinstance(chosen, str):
        raise ValueError("invalid local_model")
    if not chosen.strip():
        raise ValueError("local_model must not be empty")
    if any(c.isspace() or ord(c) < 32 for c in chosen):
        raise ValueError("local_model must not contain whitespace or control")
    if any(c in _LOCAL_MODEL_FORBIDDEN for c in chosen):
        # Reported without the value: a rejected engine name is operator
        # configuration, but it is not echoed back on the principle that a
        # diagnostic never carries the text it was given.
        raise ValueError(
            "invalid local_model; a name may not contain a quote, a backslash, "
            "a question mark, or a hash"
        )
    return chosen


@dataclass(frozen=True)
class Settings:
    jev_provider: str = "api_only"
    typesafe_base_url: str = "https://api.typesafe.ai/v1"
    openrouter_base_url: str = "https://openrouter.ai/api"
    openrouter_endpoint_path: str = "/alpha/decisions"
    jev_endpoint_path: str = "/systemone"
    jev_model: str = "jev-latest"
    openrouter_model: str = "~typesafe/jev-latest"
    laya_base_url: str = "http://127.0.0.1:8000"
    laya_endpoint_path: str = "/v1/systemone"
    # Kept for backwards compatibility. ``local_model`` supersedes it and wins
    # whenever it is set on purpose; this field is read only when ``local_model``
    # was left alone, and ``__post_init__`` rewrites it to the resolved name so
    # every existing reader of ``laya_model`` sees the engine actually sent.
    laya_model: str = Unset()
    # The local slot is a generic decision-model endpoint, not a binding to one
    # model. ``local_model`` is the engine or checkpoint name sent to that
    # server, so a different local model is a configuration change and never a
    # code change. It is deliberately not checked against a list of known
    # names: rejecting an unrecognised model would defeat the point of the slot,
    # and a new local model has to work without a release.
    local_model: str = Unset()
    # Clef is hosted per account. The base is the shared part of that path; the
    # account id is read from the environment beside the token, because it is
    # configuration a user already has rather than something to store twice.
    clef_base_url: str = "https://api.cloudflare.com/client/v4/accounts"
    clef_model: str = "clef"
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
        r"[^.!?\n]{0,400}(?:root cause|because|constraint|must|never|always)[^.!?\n]{0,400}[.!?]?",
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
    # The hosted provider a mode name pins, empty when it pins none. It is not a
    # setting an operator writes: it is derived from the mode name in
    # ``__post_init__`` so ``typesafe`` keeps meaning TypeSafe rather than
    # becoming an order resolved from ``jev_fallback_order``.
    jev_provider_pin: str = ""

    def __post_init__(self) -> None:
        resolved = resolve_mode(self.jev_provider)
        if resolved is None:
            raise invalid_provider(self.jev_provider)
        mode, pinned = resolved
        if mode != self.jev_provider:
            # An alias selects the canonical mode, so every consumer reads one
            # spelling of the arrangement and no alias string reaches a chain,
            # a diagnostic, a log line, or a URL.
            object.__setattr__(self, "jev_provider", mode)
        if pinned:
            # A name that also pinned a hosted provider keeps that pin. It is
            # stored beside the mode rather than folded into the mode string, so
            # the mode stays one of the four canonical names.
            object.__setattr__(self, "jev_provider_pin", pinned)
        local_model = resolve_local_model(self.local_model, self.laya_model)
        object.__setattr__(self, "local_model", local_model)
        # The local slot asks one server for one engine. ``local_model`` wins
        # when it was set on purpose; otherwise the backwards-compatible
        # ``laya_model`` decides, and when that is left alone the shipped
        # default applies. Recording the resolved name in ``laya_model`` keeps
        # every existing reader of that setting correct.
        object.__setattr__(self, "laya_model", local_model)
        if (
            not self.jev_fallback_order
            or len(set(self.jev_fallback_order)) != len(self.jev_fallback_order)
            or any(p not in HOSTED_PROVIDERS for p in self.jev_fallback_order)
        ):
            raise ValueError("invalid jev_fallback_order")
        if self.clef_model not in CLEF_MODELS:
            raise ValueError(
                "invalid clef_model; expected one of " + ", ".join(CLEF_MODELS)
            )
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
        endpoint(self.clef_base_url, "/" + "probe")


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
