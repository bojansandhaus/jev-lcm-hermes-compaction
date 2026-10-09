"""Three Decisions providers with bounded retries and session-local cooldowns."""

import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Mapping
from .jev_client import (
    CLEF_ACCOUNT_ENV,
    CLEF_TOKEN_ENV,
    ClefError,
    ProviderError,
    clef_question_ids,
    clef_result,
    clef_run_url,
    parse_answers,
    post,
)
from .settings import Settings, endpoint

LOG = logging.getLogger(__name__)
ENV = {
    "typesafe": "TYPESAFE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "laya": "LAYA_API_KEY",
    "clef": CLEF_TOKEN_ENV,
}
# The Cloudflare account id is not a secret: it is a path segment, it is
# configuration the operator already has in the dashboard, and nothing can be
# scored without it. It is read separately from the credential map because the
# chain decides membership on keys alone.
ACCOUNT_ENV = {"clef": CLEF_ACCOUNT_ENV}
# A provider bound to the loopback interface carries no credential requirement:
# an empty key means "send no Authorization header", not "disabled".
KEYLESS = frozenset({"laya"})
Transport = Callable[[str, str, dict[str, Any], float], Any]

# A local hop that keeps failing would otherwise turn every batch into hosted
# traffic. This breaker counts consecutive failures of the local provider and
# suppresses the hosted fallback past the limit, re-raising the local error so
# the failure stays visible and no state leaves the machine. The count lives in
# the process rather than in a chain, so it survives a rebuilt chain, and it
# resets when the process restarts. Any successful local call clears it, on the
# hosted fallback path and on the plain local path alike.
#
# The count is also bounded by silence. An outage two hours old is not evidence
# about the local server now, and a count that only a successful local call can
# clear is a count nothing clears while the fallback it gates is suppressed: the
# local hop is cooled down for `jev_fallback_cooldown_s` after every failure,
# and a rebuilt chain starts with an empty cooldown map but the same process
# count, so the breaker can outlive both the outage and the chain that saw it.
# Once the window has elapsed with no new failure the counter rearms, so the
# local server is retried and the hosted fallback is permitted again.
_LAYA_FALLBACK_FAILURE_LIMIT = 3
_LAYA_FALLBACK_WINDOW_S = 60.0
_laya_failure_lock = threading.Lock()
_laya_failure_count = 0
_laya_last_failure_at: float | None = None


def _laya_failure_recorded(now: float) -> bool:
    """Count one local failure and report whether the hosted fallback may follow."""
    global _laya_failure_count, _laya_last_failure_at
    with _laya_failure_lock:
        if (
            _laya_failure_count
            and _laya_last_failure_at is not None
            and now - _laya_last_failure_at >= _LAYA_FALLBACK_WINDOW_S
        ):
            # The window elapsed without a new failure, so the count describes
            # an outage that is over rather than one that is happening. Rearm
            # it: this failure is a first failure.
            _laya_failure_count = 0
        _laya_failure_count += 1
        _laya_last_failure_at = now
        return _laya_failure_count <= _LAYA_FALLBACK_FAILURE_LIMIT


def _laya_failure_cleared() -> None:
    """Clear the breaker after a local call answered."""
    global _laya_failure_count, _laya_last_failure_at
    with _laya_failure_lock:
        _laya_failure_count = 0
        _laya_last_failure_at = None


def laya_failure_window_s() -> float:
    """Seconds of silence after which a stalled local outage rearms the breaker."""
    return _LAYA_FALLBACK_WINDOW_S


def laya_consecutive_failures() -> int:
    """Consecutive local-hop failures this process has recorded."""
    with _laya_failure_lock:
        return _laya_failure_count


class JevProvider:
    name: str
    url: str
    model: str

    def score(
        self,
        state: Any,
        questions: dict[str, Any],
        key: str,
        timeout: float,
        transport: Transport,
    ) -> dict[str, float]:
        payload = {"model": self.model, "state": state, "questions": questions}
        return parse_answers(
            transport(self.url, key, payload, timeout), list(questions)
        )


class TypeSafeProvider(JevProvider):
    name = "typesafe"

    def __init__(self, settings: Settings):
        self.url = endpoint(settings.typesafe_base_url, settings.jev_endpoint_path)
        self.model = settings.jev_model


class LayaProvider(JevProvider):
    """A local decision-model server, reached over the Jev Decisions contract.

    ``laya-serve`` publishes ``POST /v1/systemone`` and answers with the same
    ``answers`` mapping a hosted Decisions provider returns, so this provider is
    the TypeSafe request shape pointed at loopback. Nothing leaves the machine
    and no credential is required: ``LAYA_API_KEY`` is sent only when the server
    was started with its own bearer check.

    This is the package's generic local slot rather than a binding to one model.
    The provider name stays ``laya`` because that is the mode vocabulary an
    operator already writes, while ``local_model`` selects which engine answers.
    ``Settings`` resolves that precedence once, so the value read here is the
    engine or checkpoint the operator asked for. Any local server speaking the
    same contract therefore fits this slot by configuration alone: point
    ``laya_base_url`` at it and name it in ``local_model``. No allowlist is
    applied, so a new engine works without a release.
    """

    name = "laya"

    def __init__(self, settings: Settings):
        self.url = endpoint(settings.laya_base_url, settings.laya_endpoint_path)
        self.model = settings.local_model


class ClefProvider(JevProvider):
    """Cloudflare Workers AI Clef, reached over the Jev Decisions wire contract.

    ``clef`` answers the same System One shaped typed questions as the hosted
    Jev providers, so this provider sends the same ``model``, ``state``, and
    ``questions`` body and reads the same ``answers`` mapping back. Three things
    are specific to this wire:

    - The endpoint is per account, so ``CLOUDFLARE_ACCOUNT_ID`` is configuration
      the URL cannot be built without and ``CLOUDFLARE_API_TOKEN`` is the
      credential. Both are checked before any request and the failure names the
      variable, never a value.
    - Clef constrains question ids, so ids are mapped onto its alphabet and
      mapped back before the caller sees them.
    - Clef may answer a ``choice`` or an ordered ``score`` as well as a ``noul``,
      so the response is validated against the scale each sent question declared.

    ``clef_model`` names the checkpoint: the 27B ``clef``, or ``clef-flash`` for
    a latency-bound path. Both answer the same contract, so the checkpoint is a
    setting of this one provider and never a separate chain member.
    """

    name = "clef"

    def __init__(self, settings: Settings, account: str = ""):
        self.base_url = settings.clef_base_url
        self.model = settings.clef_model
        self.account = account

    def score(
        self,
        state: Any,
        questions: dict[str, Any],
        key: str,
        timeout: float,
        transport: Transport,
    ) -> dict[str, float]:
        if not key:
            raise ClefError(
                "clef_provider selected but " + CLEF_TOKEN_ENV + " is not set",
                "401",
            )
        if not self.account:
            raise ClefError(
                "clef_provider selected but " + CLEF_ACCOUNT_ENV + " is not set",
                "401",
            )
        sent, restore = clef_question_ids(questions)
        url = clef_run_url(self.base_url, self.account, self.model)
        payload = {"model": self.model, "state": state, "questions": sent}
        try:
            response = transport(url, key, payload, timeout)
        except Exception as error:
            # Clef is a hosted route, so the state has already left the machine
            # by the time this runs. Only the exception class is logged: the
            # message of a transport failure can quote the URL, the header, or
            # the body it was carrying, and the body is the content about to be
            # compacted. The chain still records ``ProviderError.reason``, which
            # is drawn from a fixed set, so a Clef failure behaves exactly as a
            # TypeSafe failure does for fallback, cooldown, and diagnostics.
            LOG.warning("clef_provider_failed exception=%s", type(error).__name__)
            raise
        scores = parse_answers(clef_result(response), list(sent), sent)
        return {restore[wire]: value for wire, value in scores.items()}


NATIVE_DECISIONS_PATH = "/alpha/decisions"
CHAT_INSTRUCTIONS = (
    "You are a retention scorer. For every question id you are given, answer with the "
    "probability between 0 and 1 that the answer to that question is yes, judging only from "
    "the state you receive. Reply with JSON only, shaped exactly as "
    '{"answers": {"<question id>": {"noul": <number>}}}. Add no commentary.'
)
_FENCE = re.compile(r"^```[a-zA-Z0-9]*\s*|\s*```$")


class OpenRouterProvider(JevProvider):
    """Two selectable OpenRouter surfaces behind one chain.

    The default is the native Decisions surface, ``/alpha/decisions``, because
    OpenRouter refuses the Jev model anywhere else. On 2026-09-21 a request to
    ``/api/v1/chat/completions`` with the configured model returned
    ``400 ~typesafe/jev-latest is a decisions model and cannot be used with the
    chat/completions endpoint. Use the /api/alpha/decisions endpoint instead.``

    Setting ``openrouter_endpoint_path`` to any other path selects the chat
    completions surface, whose request and response are mapped through the
    adapter in ``chat_request`` and ``decisions_answers``. That surface is what a
    self-hosted or proxied gateway speaks, and it is what a scoring-capable chat
    model needs. A body that already carries a Decisions ``answers`` mapping is
    passed through untouched.
    """

    name = "openrouter"

    def __init__(self, settings: Settings):
        self.url = endpoint(
            settings.openrouter_base_url, settings.openrouter_endpoint_path
        )
        self.model = settings.openrouter_model
        self.decisions_shaped = (
            settings.openrouter_endpoint_path != NATIVE_DECISIONS_PATH
        )

    def score(
        self,
        state: Any,
        questions: dict[str, Any],
        key: str,
        timeout: float,
        transport: Transport,
    ) -> dict[str, float]:
        if not self.decisions_shaped:
            return super().score(state, questions, key, timeout, transport)
        response = transport(
            self.url, key, chat_request(self.model, state, questions), timeout
        )
        return parse_answers(decisions_answers(response), list(questions))


def chat_request(model: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    """Express a Decisions-shaped scoring request as a chat completion."""
    return {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": CHAT_INSTRUCTIONS},
            {
                "role": "user",
                "content": json.dumps(
                    {"state": state, "questions": questions},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
    }


def decisions_answers(response: Any) -> dict[str, Any]:
    """Normalize a chat completion or a Decisions body onto the Decisions shape.

    A body that already carries a non-empty ``answers`` mapping is passed through,
    which covers self-hosted or proxied gateways reachable at the configured path.
    A chat completion is unwrapped from its first choice: fenced JSON is tolerated,
    scalar answers are wrapped, and a missing, empty, or unparseable answer set is
    reported as malformed.
    """
    if not isinstance(response, dict):
        raise ProviderError("malformed")
    passthrough = response.get("answers")
    if isinstance(passthrough, dict) and passthrough:
        return {
            "answers": {
                question: value if isinstance(value, dict) else {"noul": value}
                for question, value in passthrough.items()
            }
        }
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError("malformed")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("malformed")
    try:
        parsed = json.loads(_FENCE.sub("", content.strip()))
    except ValueError as error:
        raise ProviderError("malformed") from error
    answers = parsed.get("answers") if isinstance(parsed, dict) else None
    if not isinstance(answers, dict) or not answers:
        raise ProviderError("malformed")
    return {
        "answers": {
            question: value if isinstance(value, dict) else {"noul": value}
            for question, value in answers.items()
        }
    }


class ProviderChain:
    def __init__(
        self,
        settings: Settings,
        env: Mapping[str, str] | None = None,
        transport: Transport = post,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.settings, self.transport, self.clock = settings, transport, clock
        environment = env if env is not None else os.environ
        self._keys = {
            name: environment.get(var, "").strip() for name, var in ENV.items()
        }
        self._accounts = {
            name: environment.get(var, "").strip() for name, var in ACCOUNT_ENV.items()
        }
        if settings.jev_provider == "local_only":
            # The local slot alone in place of the hosted providers: no chain to
            # fall through and no credential to find.
            self.order = ["laya"]
        elif settings.jev_provider == "local_with_api_fallback":
            # The local slot leads and the keyed hosted providers follow. This
            # mode exists to provide the fallback, so selecting it without any
            # hosted key is a load-time error rather than a quietly local-only
            # profile.
            hosted = [p for p in settings.jev_fallback_order if self._keys[p]]
            if not hosted:
                raise ValueError(
                    "local_with_api_fallback needs a hosted fallback key: "
                    + ", ".join(ENV[p] for p in settings.jev_fallback_order)
                )
            self.order = ["laya"] + hosted
        elif settings.jev_provider == "api_only":
            if settings.jev_provider_pin:
                # A pinned name names its hosted provider outright, so the
                # fallback order does not get a vote.
                pinned = settings.jev_provider_pin
                self._require_credential(pinned)
                self.order = [pinned]
            else:
                # The hosted chain contains only providers with a usable key.
                # The keyless local slot is never selected on its own
                # initiative, which is what keeps the default mode's behaviour
                # exactly as it was.
                self.order = [p for p in settings.jev_fallback_order if self._keys[p]]
        else:
            # api_with_local_fallback: the hosted providers lead, in the order
            # that already exists here, and the local slot is the last resort.
            # It is a two-provider chain, so it uses the existing cooldown,
            # trigger, and breaker machinery unchanged.
            hosted = [p for p in settings.jev_fallback_order if self._keys[p]]
            if not hosted:
                raise ValueError(
                    "api_with_local_fallback needs a hosted key: "
                    + ", ".join(ENV[p] for p in settings.jev_fallback_order)
                )
            self.order = hosted + ["laya"]
        if not settings.jev_fallback_enabled:
            self.order = self.order[:1]
        self.providers: dict[str, JevProvider] = {
            "typesafe": TypeSafeProvider(settings),
            "openrouter": OpenRouterProvider(settings),
            "laya": LayaProvider(settings),
            "clef": ClefProvider(settings, self._accounts.get("clef", "")),
        }
        self.cooldowns: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.last_provider = ""
        self.fallback_count = 0
        self.calls = 0

    def _require_credential(self, provider: str) -> None:
        """Fail at load when a pinned provider has no usable route.

        A pinned provider promises a usable route, so its credential and, where
        the route needs one, its account id are checked at load beside each
        other. In a chain the membership decision is made on keys alone, so a
        member without an account id joins and then refuses each request
        instead, naming the same variable.
        """
        if not self._keys[provider]:
            raise ValueError("missing " + ENV[provider])
        if provider in ACCOUNT_ENV and not self._accounts[provider]:
            raise ValueError("missing " + ACCOUNT_ENV[provider])

    def diagnostics(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "keys_present": [ENV[p] for p in ENV if self._keys[p]],
            "configuration_present": [
                var for name, var in ACCOUNT_ENV.items() if self._accounts.get(name)
            ],
            "cooldown_seconds": {
                p: max(0.0, t - self.clock()) for p, t in self.cooldowns.items()
            },
            "last_errors": self.errors,
            "last_provider": self.last_provider,
            "laya_consecutive_failures": laya_consecutive_failures(),
            "laya_failure_window_s": laya_failure_window_s(),
        }

    def score(self, state: Any, questions: dict[str, Any]) -> dict[str, float]:
        if not self.order:
            raise ProviderError("disabled")
        available = [p for p in self.order if self.cooldowns.get(p, 0) <= self.clock()]
        if not available:
            raise ProviderError("cooldown")
        previous = self.order[0]
        last = ProviderError("cooldown")
        for index, name in enumerate(available):
            if name != self.order[0]:
                self.fallback_count += 1
                LOG.warning(
                    "jev_provider_fallback from=%s to=%s reason=%s",
                    previous,
                    name,
                    self.errors.get(previous, "cooldown"),
                )
            attempts = (
                1
                if index + 1 < len(available)
                else 1 + self.settings.jev_fallback_max_retries
            )
            for attempt in range(attempts):
                self.calls += 1
                try:
                    scores = self.providers[name].score(
                        state,
                        questions,
                        self._keys[name],
                        self.settings.request_timeout_s,
                        self.transport,
                    )
                except ProviderError as error:
                    last = error
                except Exception:
                    last = ProviderError("transport_error")
                else:
                    self.last_provider = name
                    self.errors.pop(name, None)
                    if name == "laya":
                        _laya_failure_cleared()
                    return scores
                self.errors[name] = last.reason
                if last.reason not in self.settings.jev_fallback_on:
                    raise last
                if name == "laya" and index + 1 < len(available):
                    # The local hop failed where the hosted fallback would
                    # follow. Past the limit the fallback is suppressed and the
                    # local error is re-raised instead of being answered
                    # remotely, so repeated local failures stop turning every
                    # batch into hosted traffic.
                    if not _laya_failure_recorded(self.clock()):
                        LOG.warning(
                            "laya_fallback_suppressed after %d consecutive local failures",
                            _LAYA_FALLBACK_FAILURE_LIMIT,
                        )
                        raise last
            self.cooldowns[name] = self.clock() + self.settings.jev_fallback_cooldown_s
            previous = name
        raise last
