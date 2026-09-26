"""Two Decisions providers with bounded retries and session-local cooldowns."""

import json
import logging
import os
import re
import time
from typing import Any, Callable, Mapping
from .jev_client import ProviderError, parse_answers, post
from .settings import Settings, endpoint

LOG = logging.getLogger(__name__)
ENV = {
    "typesafe": "TYPESAFE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "laya": "LAYA_API_KEY",
}
# A provider bound to the loopback interface carries no credential requirement:
# an empty key means "send no Authorization header", not "disabled".
KEYLESS = frozenset({"laya"})
Transport = Callable[[str, str, dict[str, Any], float], Any]


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
    """A local Laya server, reached over the Jev Decisions wire contract.

    ``laya-serve`` publishes ``POST /v1/systemone`` and answers with the same
    ``answers`` mapping a hosted Decisions provider returns, so this provider is
    the TypeSafe request shape pointed at loopback. Nothing leaves the machine
    and no credential is required: ``LAYA_API_KEY`` is sent only when the server
    was started with its own bearer check.

    ``laya_model`` names a Laya checkpoint (``english``, ``multilingual``,
    ``typed-decisions``, or the published repository ids). Any other value,
    including a Jev model identifier, makes the server choose a checkpoint from
    the script and language of the state.
    """

    name = "laya"

    def __init__(self, settings: Settings):
        self.url = endpoint(settings.laya_base_url, settings.laya_endpoint_path)
        self.model = settings.laya_model


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
        self._keys = {
            name: (env if env is not None else os.environ).get(var, "").strip()
            for name, var in ENV.items()
        }
        if settings.jev_provider == "laya":
            # Laya runs locally in place of the hosted Jev providers, so the
            # local mode has no chain to fall through and no credential to find.
            self.order = ["laya"]
        elif settings.jev_provider == "laya_then_hosted":
            # Laya leads and the keyed hosted providers follow. This mode exists
            # to provide the fallback, so selecting it without any hosted key is
            # a load-time error rather than a quietly local-only profile.
            hosted = [p for p in settings.jev_fallback_order if self._keys[p]]
            if not hosted:
                raise ValueError(
                    "laya_then_hosted needs a hosted fallback key: "
                    + ", ".join(ENV[p] for p in settings.jev_fallback_order)
                )
            self.order = ["laya"] + hosted
        elif settings.jev_provider == "auto":
            # The hosted chain contains only providers with a usable key. The
            # keyless local provider is never selected on its own initiative.
            self.order = [p for p in settings.jev_fallback_order if self._keys[p]]
        else:
            if not self._keys[settings.jev_provider]:
                raise ValueError("missing " + ENV[settings.jev_provider])
            self.order = [settings.jev_provider]
        if not settings.jev_fallback_enabled:
            self.order = self.order[:1]
        self.providers: dict[str, JevProvider] = {
            "typesafe": TypeSafeProvider(settings),
            "openrouter": OpenRouterProvider(settings),
            "laya": LayaProvider(settings),
        }
        self.cooldowns: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.last_provider = ""
        self.fallback_count = 0
        self.calls = 0

    def diagnostics(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "keys_present": [ENV[p] for p in ENV if self._keys[p]],
            "cooldown_seconds": {
                p: max(0.0, t - self.clock()) for p, t in self.cooldowns.items()
            },
            "last_errors": self.errors,
            "last_provider": self.last_provider,
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
                    return scores
                self.errors[name] = last.reason
                if last.reason not in self.settings.jev_fallback_on:
                    raise last
            self.cooldowns[name] = self.clock() + self.settings.jev_fallback_cooldown_s
            previous = name
        raise last
