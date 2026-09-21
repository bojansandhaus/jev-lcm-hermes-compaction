"""Two Decisions providers with bounded retries and session-local cooldowns."""

import logging
import os
import time
from typing import Any, Callable, Mapping
from .jev_client import ProviderError, parse_answers, post
from .settings import Settings, endpoint

LOG = logging.getLogger(__name__)
ENV = {"typesafe": "TYPESAFE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
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


class OpenRouterProvider(JevProvider):
    name = "openrouter"

    def __init__(self, settings: Settings):
        self.url = endpoint(settings.openrouter_base_url, "/alpha/decisions")
        self.model = settings.openrouter_model


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
        configured = (
            settings.jev_fallback_order
            if settings.jev_provider == "auto"
            else (settings.jev_provider,)
        )
        if settings.jev_provider != "auto" and not self._keys[settings.jev_provider]:
            raise ValueError("missing " + ENV[settings.jev_provider])
        self.order = [p for p in configured if self._keys[p]]
        if not settings.jev_fallback_enabled:
            self.order = self.order[:1]
        self.providers: dict[str, JevProvider] = {
            "typesafe": TypeSafeProvider(settings),
            "openrouter": OpenRouterProvider(settings),
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
