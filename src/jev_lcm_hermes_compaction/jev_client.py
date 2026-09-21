"""Strict Decisions wire parsing, without echoed provider bodies."""
import json
import socket
import urllib.error
import urllib.request
from typing import Any


class ProviderError(Exception):
    def __init__(self, reason: str):
        allowed = {"transport_error", "timeout", "401", "403", "429", "5xx", "http_error", "malformed", "disabled", "cooldown"}
        self.reason = reason if reason in allowed else "transport_error"
        super().__init__(self.reason)


def parse_answers(data: Any, expected: list[str]) -> dict[str, float]:
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ProviderError("malformed")
    out = {}
    for name in expected:
        answer = data["answers"].get(name)
        value = answer.get("noul") if isinstance(answer, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ProviderError("malformed")
        out[name] = float(value)
    return out


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def post(url: str, key: str, payload: dict[str, Any], timeout: float) -> Any:
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ProviderError("malformed")
            return json.loads(body)
    except urllib.error.HTTPError as error:
        raise ProviderError(str(error.code) if error.code in (401, 403, 429) else "5xx" if error.code >= 500 else "http_error") from None
    except (TimeoutError, socket.timeout):
        raise ProviderError("timeout") from None
    except (ValueError, UnicodeError):
        raise ProviderError("malformed") from None
    except urllib.error.URLError:
        raise ProviderError("transport_error") from None
