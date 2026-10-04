"""Strict Decisions wire parsing, without echoed provider bodies."""

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping
from urllib.parse import urlsplit

# Clef is served from Cloudflare Workers AI at a per-account endpoint. The
# account id is configuration rather than a credential, but a request cannot be
# built without it, so it is read from the environment beside the token and
# neither value is ever written to a file, a log line, or an error message.
CLEF_ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
CLEF_TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
CLEF_BASE = "https://api.cloudflare.com/client/v4/accounts"
CLEF_RUN_PATH = "/{account}/ai/run/@cf/cloudflare/{model}"
CLEF_MODELS = ("clef", "clef-flash")
CLEF_ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
CLEF_ID_LIMIT = 100
CLEF_MAX_QUESTIONS = 64
_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ProviderError(Exception):
    def __init__(self, reason: str):
        allowed = {
            "transport_error",
            "timeout",
            "401",
            "403",
            "429",
            "5xx",
            "http_error",
            "malformed",
            "disabled",
            "cooldown",
        }
        self.reason = reason if reason in allowed else "transport_error"
        super().__init__(self.reason)


class ClefError(ProviderError):
    """A Clef failure whose message names the cause, never the reviewed content.

    ``ProviderError.reason`` stays inside its fixed vocabulary, so the chain's
    fallback, cooldown, and diagnostics behaviour is identical for Clef and for
    every other provider. This subclass adds one thing: a message an operator can
    act on, such as the variable that is missing or the code Cloudflare refused
    with. Only names, counts, and provider codes ever reach it.
    """

    def __init__(self, message: str, reason: str = "http_error"):
        super().__init__(reason)
        self.message = message

    def __str__(self) -> str:
        return self.message


def index_scale(criteria: Any) -> tuple[float, float]:
    """The inclusive bounds of the scale an ordered ``criteria`` list describes.

    A ``noul`` question carries no criteria and is a two-point scale, so a
    probability is bounded by this same helper rather than by a second copy of
    the range check. An ordered ``score`` or ``choice`` question has one point
    per criterion, so its index runs from zero to one less than the number of
    criteria, and a scale that cannot describe a choice is malformed rather than
    silently permissive.
    """
    if criteria is None:
        return 0.0, 1.0
    size = len(criteria) if isinstance(criteria, (Mapping, list, tuple)) else 0
    if size < 2:
        raise ProviderError("malformed")
    return 0.0, float(size - 1)


def answer_value(answer: Any, question: Any) -> float:
    """Reduce one typed answer to a number, validated against its own scale.

    ``noul`` answers with a probability, ``choice`` with the label of the
    selected option, and ``score`` with an index on the ordered ``criteria``
    scale. Each is checked against the bounds ``index_scale`` derives once, and
    each is reported at its own position: a probability stays a probability and
    an index-scale answer keeps its scale instead of being divided into ``0..1``.
    """
    if not isinstance(answer, dict):
        raise ProviderError("malformed")
    spec = question if isinstance(question, dict) else {}
    kind = spec.get("type")
    criteria = spec.get("criteria")
    if kind == "choice":
        labels = list(criteria) if isinstance(criteria, (Mapping, list, tuple)) else []
        choice = answer.get("choice")
        if not labels or choice not in labels:
            raise ProviderError("malformed")
        return float(labels.index(choice))
    value = answer.get("score") if kind == "score" else answer.get("noul")
    low, high = index_scale(criteria)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not low <= value <= high
    ):
        raise ProviderError("malformed")
    return float(value)


def parse_answers(
    data: Any,
    expected: list[str],
    questions: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Validate the answers the caller asked for, in the caller's own spelling.

    ``questions`` is optional. Without it every expected id is read as a
    ``noul`` question on a ``0..1`` scale, which is what every provider other
    than Clef returns. Clef passes the question definitions it sent, so a
    ``choice`` or ``score`` answer is checked against the scale that question
    actually declared.
    """
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ProviderError("malformed")
    out = {}
    for name in expected:
        spec = questions.get(name) if isinstance(questions, Mapping) else None
        out[name] = answer_value(data["answers"].get(name), spec)
    return out


def clef_account(account: str) -> str:
    """Validate a Cloudflare account id before it can reach a URL or a header.

    The id is configuration, not a secret, and it is interpolated into the
    request path, so it is held to the same narrow shape every provider endpoint
    is held to: no separator, no traversal, no control character, bounded
    length. The error names the variable, never a value.
    """
    value = str(account or "").strip()
    if not _ACCOUNT_ID.fullmatch(value):
        raise ClefError(
            "invalid " + CLEF_ACCOUNT_ENV + "; expected 1 to 64 characters of "
            "A-Z, a-z, 0-9, '_' or '-'",
            "malformed",
        )
    return value


def clef_run_url(base: str, account: str, model: str) -> str:
    """The hosted Clef endpoint for one account and one checkpoint."""
    if model not in CLEF_MODELS:
        raise ClefError(
            "clef_model must be one of: " + ", ".join(CLEF_MODELS), "malformed"
        )
    path = CLEF_RUN_PATH.format(account=clef_account(account), model=model)
    parsed = urlsplit(base)
    if "\\" in path or "?" in path or "#" in path or ".." in path:
        raise ClefError("invalid Cloudflare account path", "malformed")
    if parsed.scheme != "https" or not parsed.netloc or parsed.query:
        raise ClefError("invalid Cloudflare endpoint", "malformed")
    return base.rstrip("/") + path


def clef_question_ids(
    questions: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Map caller question ids onto ids Clef accepts, and the way back.

    Clef accepts letters, digits, ``_``, ``.``, and ``-`` in a question id, at
    most ``CLEF_ID_LIMIT`` characters, and at most ``CLEF_MAX_QUESTIONS``
    questions per request. This package builds ids as ``<sha256>:<name>``, so
    the colon this package has always sent is illegal on this wire. An id that
    already fits keeps it; anything else is renamed to ``clefq<n>``.

    Every caller id is reserved before any generated name is handed out, so a
    generated id can never shadow a caller's own question and two questions
    cannot collapse onto one answer. The second return value maps each wire id
    back to the caller's spelling, which is why no caller ever observes a
    rename.
    """
    names = list(questions)
    if len(names) > CLEF_MAX_QUESTIONS:
        # Failing loudly beats dropping questions: a silently shortened batch
        # would leave candidates unscored without saying so.
        raise ClefError(
            "Clef accepts at most "
            + str(CLEF_MAX_QUESTIONS)
            + " questions per request, got "
            + str(len(names))
            + "; lower jev_max_candidates_per_batch",
            "malformed",
        )
    reserved = set(names)
    taken: set[str] = set()
    sent: dict[str, Any] = {}
    restore: dict[str, str] = {}
    for name in names:
        if CLEF_ID.fullmatch(name) and name not in taken:
            wire = name
        else:
            wire = "clefq" + str(len(restore))
            suffix = 2
            while wire in reserved or wire in taken:
                wire = "clefq" + str(len(restore)) + "_" + str(suffix)
                suffix += 1
        taken.add(wire)
        sent[wire] = questions[name]
        restore[wire] = name
    return sent, restore


def clef_result(data: Any) -> dict[str, Any]:
    """Unwrap a Clef response onto the Decisions ``answers`` shape.

    Cloudflare serves Clef from a REST endpoint whose body is the model output
    itself, while its general API surface wraps results in a
    ``success``/``result`` envelope. Both are accepted and the top-level
    ``answers`` mapping wins, so a body carrying both is read the same way
    twice. A ``success: false`` envelope carries Cloudflare's own error codes,
    which are more useful than a parse failure, so they are surfaced verbatim.
    """
    if not isinstance(data, dict):
        raise ClefError(
            "Cloudflare Workers AI returned a non-object response", "malformed"
        )
    if data.get("success") is False:
        codes = [
            str(error.get("code"))
            for error in (data.get("errors") or [])
            if isinstance(error, dict) and error.get("code") is not None
        ]
        detail = ", ".join(codes) if codes else "no code"
        raise ClefError(
            "Cloudflare Workers AI refused the request (code " + detail + ")",
            "http_error",
        )
    answers = data.get("answers")
    if not isinstance(answers, dict):
        result = data.get("result")
        answers = result.get("answers") if isinstance(result, dict) else None
    if not isinstance(answers, dict):
        raise ClefError(
            "Cloudflare Workers AI returned no answers mapping", "malformed"
        )
    return {"answers": answers}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def post(url: str, key: str, payload: dict[str, Any], timeout: float) -> Any:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=timeout
        ) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ProviderError("malformed")
            return json.loads(body)
    except urllib.error.HTTPError as error:
        raise ProviderError(
            str(error.code)
            if error.code in (401, 403, 429)
            else "5xx" if error.code >= 500 else "http_error"
        ) from None
    except (TimeoutError, socket.timeout):
        raise ProviderError("timeout") from None
    except (ValueError, UnicodeError):
        raise ProviderError("malformed") from None
    except urllib.error.URLError:
        raise ProviderError("transport_error") from None
