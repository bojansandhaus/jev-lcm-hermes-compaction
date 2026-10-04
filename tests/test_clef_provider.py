"""Cloudflare Clef as a Decisions provider: wire shape, envelopes, privacy.

Clef is a hosted decision model served from Cloudflare Workers AI at a
per-account endpoint. It answers the same System One shaped typed questions as
the other providers, so it is selected the same way, joins the same chain, and
fails on the same triggers. Two things are new and are pinned here:

1. The reviewed content leaves the machine. Selecting Clef sends the scored
   state to ``api.cloudflare.com``, so nothing on this path may log the state,
   the candidate text, the token, or the account id.
2. Clef constrains question ids to letters, digits, ``_``, ``.``, and ``-``, at
   most 100 characters, at most 64 per request. This package builds ids as
   ``<sha256>:<name>``, so the colon is always illegal and every real id has to
   be mapped and mapped back.

No Cloudflare credential on the build machine is authorized for Workers AI, so
every request here is made against an injected transport. No test below sends
anything off the machine, and none of them asserts live Clef behaviour.
"""

import logging
import re

import pytest

from jev_lcm_hermes_compaction.jev_client import (
    ClefError,
    ProviderError,
    index_scale,
)
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
ACCOUNT = "0123456789abcdef0123456789abcdef"
CREDENTIALS = {TOKEN_ENV: "private-token", ACCOUNT_ENV: ACCOUNT}
TYPESAFE = "https://api.typesafe.ai/v1/systemone"
OPENROUTER = "https://openrouter.ai/api/alpha/decisions"
LOCAL = "http://127.0.0.1:8000/v1/systemone"
CLEF = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/@cf/cloudflare/clef"
CLEF_FLASH = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
    "/ai/run/@cf/cloudflare/clef-flash"
)
BOTH_KEYS = {
    "TYPESAFE_API_KEY": "private-one",
    "OPENROUTER_API_KEY": "private-two",
    **CREDENTIALS,
}
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
QUESTIONS = {"probe:keep_result": {"type": "noul", "instructions": "keep?"}}


def answering(url, key, payload, timeout):
    """Answer every sent question id, honouring whatever id was actually used."""
    del url, key, timeout
    return {"answers": {q: {"noul": 0.25} for q in payload["questions"]}}


def recorder(seen, response=None):
    def transport(url, key, payload, timeout):
        seen.append((url, key, payload, timeout))
        return (
            response(url, payload)
            if response
            else answering(url, key, payload, timeout)
        )

    return transport


def test_clef_alone_sends_no_request_to_jev_or_laya():
    """Every other provider holds a key, and none of them is contacted."""
    seen = []
    chain = ProviderChain(Settings(jev_provider="clef"), BOTH_KEYS, recorder(seen))
    assert chain.order == ["clef"]
    assert chain.score({}, QUESTIONS) == {"probe:keep_result": 0.25}
    assert [url for url, _, _, _ in seen] == [CLEF]
    assert chain.last_provider == "clef"
    assert chain.fallback_count == 0
    assert TYPESAFE not in str(seen)
    assert OPENROUTER not in str(seen)
    assert LOCAL not in str(seen)


def test_clef_alone_is_the_same_chain_as_the_mode_alias():
    aliased = ProviderChain(Settings(jev_provider="clef_api"), BOTH_KEYS, recorder([]))
    canonical = ProviderChain(Settings(jev_provider="clef"), BOTH_KEYS, recorder([]))
    assert aliased.order == canonical.order == ["clef"]
    assert aliased.diagnostics() == canonical.diagnostics()
    assert Settings(jev_provider="clef_api").jev_provider == "clef"


def test_the_account_and_the_token_are_read_from_the_environment_and_not_logged():
    seen = []
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder(seen))
    chain.score({"history": []}, QUESTIONS)
    url, key, payload, timeout = seen[0]
    assert key == "private-token"
    assert ACCOUNT in url
    assert set(payload) == {"model", "state", "questions"}
    assert payload["model"] == "clef"
    assert payload["state"] == {"history": []}
    assert timeout == Settings().request_timeout_s
    assert "private-token" not in repr(chain.diagnostics())
    assert ACCOUNT not in repr(chain.diagnostics())
    # The token is a credential and the account id is configuration. Both are
    # reported by name, in separate fields, and neither by value.
    assert chain.diagnostics()["keys_present"] == [TOKEN_ENV]
    assert chain.diagnostics()["configuration_present"] == [ACCOUNT_ENV]


def test_clef_joins_the_fallback_order_and_the_hosted_chain():
    """The existing chain machinery, unchanged, carries the new provider."""
    assert Settings(jev_fallback_order=("clef", "typesafe", "openrouter"))
    order = ProviderChain(
        Settings(jev_fallback_order=("clef", "typesafe", "openrouter")),
        BOTH_KEYS,
        recorder([]),
    ).order
    assert order == ["clef", "typesafe", "openrouter"]
    # An uncredentialed Clef is filtered out of an unordered chain exactly as
    # an uncredentialed TypeSafe is, so auto is unaffected by its presence.
    assert ProviderChain(Settings(), BOTH_KEYS, recorder([])).order == [
        "typesafe",
        "openrouter",
    ]
    assert (
        ProviderChain(
            Settings(jev_fallback_order=("clef", "typesafe")), {}, recorder([])
        ).order
        == []
    )


def test_a_credentialed_clef_failure_falls_through_on_the_configured_triggers():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        if "cloudflare" in url:
            raise ProviderError("429")
        return answering(url, key, payload, timeout)

    chain = ProviderChain(
        Settings(jev_fallback_order=("clef", "typesafe", "openrouter")),
        BOTH_KEYS,
        transport,
    )
    assert chain.score({}, QUESTIONS) == {"probe:keep_result": 0.25}
    assert seen == [CLEF, TYPESAFE]
    assert chain.fallback_count == 1
    assert chain.diagnostics()["last_errors"] == {"clef": "429"}


def test_clef_flash_routes_to_the_flash_endpoint_and_the_flash_model():
    """The checkpoint is a setting of one provider, not a second provider."""
    seen = []
    chain = ProviderChain(
        Settings(jev_provider="clef", clef_model="clef-flash"),
        CREDENTIALS,
        recorder(seen),
    )
    assert chain.order == ["clef"]
    chain.score({}, QUESTIONS)
    url, _, payload, _ = seen[0]
    assert url == CLEF_FLASH
    assert payload["model"] == "clef-flash"
    assert Settings().clef_model == "clef"
    with pytest.raises(ValueError, match="clef_model"):
        Settings(clef_model="clef-xl")
    assert Settings(clef_model="clef-flash").clef_model == "clef-flash"


def test_both_response_envelopes_parse():
    """The bare model output, and Cloudflare's REST envelope around it."""
    bare = recorder(
        [],
        lambda url, payload: {
            "model": "clef",
            "answers": {q: {"noul": 0.31} for q in payload["questions"]},
            "usage": {"input_tokens": 12},
        },
    )
    enveloped = recorder(
        [],
        lambda url, payload: {
            "success": True,
            "result": {
                "model": "clef",
                "answers": {q: {"noul": 0.62} for q in payload["questions"]},
                "usage": {"input_tokens": 12},
            },
            "errors": [],
            "messages": [],
        },
    )
    for transport, expected in ((bare, 0.31), (enveloped, 0.62)):
        chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, transport)
        assert chain.score({}, QUESTIONS) == {"probe:keep_result": expected}
        assert chain.last_provider == "clef"


def test_a_top_level_answers_mapping_is_preferred_over_the_envelope():
    both = recorder(
        [],
        lambda url, payload: {
            "success": True,
            "answers": {q: {"noul": 0.11} for q in payload["questions"]},
            "result": {"answers": {q: {"noul": 0.99} for q in payload["questions"]}},
        },
    )
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, both)
    assert chain.score({}, QUESTIONS) == {"probe:keep_result": 0.11}


def test_success_false_raises_with_cloudflares_own_code():
    refused = recorder(
        [],
        lambda url, payload: {
            "success": False,
            "errors": [
                {"code": 7003, "message": "Authentication error"},
                {"code": 10000, "message": "workers ai binding missing"},
            ],
            "result": None,
        },
    )
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, refused)
    with pytest.raises(ClefError) as error:
        chain.score({}, QUESTIONS)
    message = str(error.value)
    assert "7003" in message and "10000" in message
    # A refusal is not a parse accident. The reason stays inside the vocabulary
    # the chain already knows, so Cloudflare's code rides in the message and the
    # fallback, cooldown, and diagnostics behaviour is unchanged.
    assert error.value.reason == "http_error"
    assert chain.errors["clef"] == "http_error"


def test_a_success_false_envelope_without_a_code_still_names_the_provider():
    chain = ProviderChain(
        Settings(jev_provider="clef"),
        CREDENTIALS,
        recorder([], lambda url, payload: {"success": False, "errors": []}),
    )
    with pytest.raises(ClefError) as error:
        chain.score({}, QUESTIONS)
    assert "Cloudflare" in str(error.value)


def test_a_response_without_any_answers_mapping_is_rejected():
    for body in ({"result": {"usage": {}}}, {"answers": "no"}, {}, {"result": 7}):
        chain = ProviderChain(
            Settings(jev_provider="clef"),
            CREDENTIALS,
            recorder([], lambda url, payload, body=body: body),
        )
        # The message names Cloudflare and the shape it wanted; the reason stays
        # inside the chain's vocabulary, so this is still a plain malformed.
        with pytest.raises(ClefError) as error:
            chain.score({}, QUESTIONS)
        assert error.value.reason == "malformed"
        assert "Cloudflare" in str(error.value)


@pytest.mark.parametrize(
    "env,missing",
    [
        ({TOKEN_ENV: "private-token"}, ACCOUNT_ENV),
        ({ACCOUNT_ENV: ACCOUNT}, TOKEN_ENV),
        ({}, TOKEN_ENV),
        ({ACCOUNT_ENV: "  "}, TOKEN_ENV),
    ],
)
def test_a_missing_credential_fails_before_any_network_call_naming_the_variable(
    env, missing
):
    """A pinned Clef refuses at load, so a request is never even attempted."""
    seen = []

    def unreachable(url, key, payload, timeout):
        seen.append(url)
        raise AssertionError("no request may be attempted")

    with pytest.raises(ValueError) as error:
        ProviderChain(Settings(jev_provider="clef"), env, unreachable)
    assert missing in str(error.value)
    assert seen == []
    assert "private-token" not in str(error.value)
    assert ACCOUNT not in str(error.value)


@pytest.mark.parametrize(
    "bad", ["../secrets", "acc count", "acc/ount", "x" * 65, "acc?a=b", "acc#f"]
)
def test_an_account_id_that_could_rewrite_the_path_is_refused_before_any_request(bad):
    """The account id is a path segment, so it is held to a narrow shape."""
    seen = []
    chain = ProviderChain(
        Settings(jev_provider="clef"),
        {TOKEN_ENV: "private-token", ACCOUNT_ENV: bad},
        recorder(seen),
    )
    with pytest.raises(ClefError, match=ACCOUNT_ENV):
        chain.score({}, QUESTIONS)
    assert seen == []


def test_an_account_id_is_only_ever_a_path_segment_in_a_https_url():
    from jev_lcm_hermes_compaction.jev_client import clef_run_url

    assert clef_run_url(Settings().clef_base_url, ACCOUNT, "clef") == CLEF
    assert clef_run_url(Settings().clef_base_url, ACCOUNT, "clef-flash") == CLEF_FLASH
    with pytest.raises(ClefError, match="clef_model"):
        clef_run_url(Settings().clef_base_url, ACCOUNT, "clef-large")


def test_a_disallowed_question_id_is_mapped_and_the_answer_restored():
    """The caller never learns that its question was renamed on the wire."""
    seen = []
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder(seen))
    sent = {
        "probe:keep_result": {"type": "noul", "instructions": "keep?"},
        "already_safe.1-2_3": {"type": "noul", "instructions": "keep?"},
        "b" * 140: {"type": "noul", "instructions": "keep?"},
        "sp ace/slash": {"type": "noul", "instructions": "keep?"},
    }
    scores = chain.score({}, sent)
    assert scores == {name: 0.25 for name in sent}
    assert list(scores) == list(sent)
    wire_ids = list(seen[0][2]["questions"])
    assert all(SAFE_ID.fullmatch(name) for name in wire_ids)
    assert len(set(wire_ids)) == len(wire_ids)
    # An id Clef already accepts travels unchanged; the rest are renamed, and
    # the caller's own spelling reaches the model inside the instruction text
    # rather than through the id.
    assert "already_safe.1-2_3" in wire_ids
    assert "probe:keep_result" not in wire_ids
    assert all(name not in wire_ids for name in ("b" * 140, "sp ace/slash"))


def test_the_caller_id_reaches_the_model_inside_the_instructions():
    """A rename must not cost the model the id the caller scored by."""
    seen = []
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder(seen))
    identity = "9f3c2a57b41d:anchor_keep"
    chain.score(
        {},
        {identity: {"type": "noul", "instructions": "Candidate id: " + identity}},
    )
    wire = seen[0][2]["questions"]
    assert list(wire) != [identity]
    assert identity in wire[list(wire)[0]]["instructions"]


def test_a_mapped_id_does_not_shadow_a_question_that_looks_alike():
    """A generated name can never collide with a caller's own question."""
    seen = []
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder(seen))
    sent = {
        "clefq0": {"type": "noul", "instructions": "first"},
        "a:b": {"type": "noul", "instructions": "second"},
        "clefq1": {"type": "noul", "instructions": "third"},
    }
    scores = chain.score({}, sent)
    assert scores == {name: 0.25 for name in sent}
    assert list(scores) == list(sent)
    wire_ids = list(seen[0][2]["questions"])
    assert len(set(wire_ids)) == 3
    assert "a:b" not in wire_ids
    # Both caller ids were reserved before any generated name was handed out.
    assert "clefq0" in wire_ids and "clefq1" in wire_ids


def test_more_questions_than_clef_accepts_fails_loudly_before_any_request():
    seen = []
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder(seen))
    too_many = {
        f"c{i}:keep_result": {"type": "noul", "instructions": "keep?"}
        for i in range(65)
    }
    with pytest.raises(ClefError) as error:
        chain.score({}, too_many)
    assert "64" in str(error.value)
    assert "jev_max_candidates_per_batch" in str(error.value)
    assert seen == []
    exactly = {f"c{i}:keep_result": {"type": "noul"} for i in range(64)}
    assert len(chain.score({}, exactly)) == 64
    assert len(seen) == 1


def test_an_unknown_choice_is_rejected():
    choice_question = {
        "goal:kind": {"type": "choice", "criteria": {"a": "A.", "b": "B."}}
    }
    for choice in ("confident", "", None, 3, ["a"]):
        chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
        chain.transport = recorder(
            [],
            lambda url, payload, c=choice: {
                "answers": {q: {"choice": c} for q in payload["questions"]}
            },
        )
        with pytest.raises(ProviderError) as error:
            chain.score({}, choice_question)
        assert error.value.reason == "malformed"
    # A choice with no criteria cannot describe one, so it cannot be accepted.
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
    chain.transport = recorder(
        [],
        lambda url, payload: {
            "answers": {q: {"choice": "a"} for q in payload["questions"]}
        },
    )
    with pytest.raises(ProviderError):
        chain.score({}, {"goal:kind": {"type": "choice"}})


def test_a_known_choice_is_accepted_at_its_position_on_its_own_scale():
    """A label is reported as its index, so an ordinal question stays ordinal."""
    criteria = {"a": "A.", "b": "B.", "c": "C."}
    for index, label in enumerate(("a", "b", "c")):
        chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
        chain.transport = recorder(
            [],
            lambda url, payload, l=label: {
                "answers": {q: {"choice": l} for q in payload["questions"]}
            },
        )
        assert chain.score(
            {}, {"goal:kind": {"type": "choice", "criteria": criteria}}
        ) == {"goal:kind": float(index)}


def test_an_out_of_range_index_scale_score_is_rejected():
    assert index_scale(["low", "mid", "high"]) == (0.0, 2.0)
    assert index_scale({"low": "L.", "high": "H."}) == (0.0, 1.0)
    assert index_scale(None) == (0.0, 1.0)
    for bad in (-0.1, 3, 4, True, "1", None):
        chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
        chain.transport = recorder(
            [],
            lambda url, payload, b=bad: {
                "answers": {q: {"score": b} for q in payload["questions"]}
            },
        )
        with pytest.raises(ProviderError) as error:
            chain.score(
                {},
                {"keep:how": {"type": "score", "criteria": ["low", "mid", "high"]}},
            )
        assert error.value.reason == "malformed"


def test_an_in_range_index_scale_score_is_accepted_at_its_own_scale():
    """Bounds come from the scale the question declared, not from a constant."""
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
    chain.transport = recorder(
        [],
        lambda url, payload: {
            "answers": {
                q: {"score": 2, "legend": ["low", "mid", "high"]}
                for q in payload["questions"]
            }
        },
    )
    assert chain.score(
        {}, {"keep:how": {"type": "score", "criteria": ["low", "mid", "high"]}}
    ) == {"keep:how": 2.0}
    # The same value is out of range on a two-point scale, which is the whole
    # point of deriving the bounds rather than reusing a constant.
    chain.transport = recorder(
        [],
        lambda url, payload: {
            "answers": {q: {"score": 2} for q in payload["questions"]}
        },
    )
    with pytest.raises(ProviderError):
        chain.score({}, {"keep:how": {"type": "score", "criteria": ["low", "high"]}})


def test_a_criteria_list_too_short_to_score_is_rejected():
    with pytest.raises(ProviderError):
        index_scale(["only"])


def test_a_probability_answer_outside_zero_to_one_is_rejected():
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
    for bad in (1.4, -0.1, True, "0.5"):
        chain.transport = recorder(
            [],
            lambda url, payload, b=bad: {
                "answers": {q: {"noul": b} for q in payload["questions"]}
            },
        )
        with pytest.raises(ProviderError, match="malformed"):
            chain.score({}, QUESTIONS)


def test_credentials_and_reviewed_content_never_reach_the_log(caplog):
    """The content about to be compacted is the most sensitive thing here."""
    sentinel = "SENTINEL-9f3c2a57"

    def transport(url, key, payload, timeout):
        raise RuntimeError(
            "transport failed for "
            + key
            + " at "
            + url
            + " with state "
            + str(payload["state"])
        )

    settings = Settings(jev_provider="clef")
    chain = ProviderChain(settings, CREDENTIALS, transport)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(Exception):
            chain.score(
                {"history": [{"role": "user", "content": sentinel + " keep verbatim"}]},
                {sentinel + ":keep_result": {"type": "noul", "instructions": sentinel}},
            )
    assert "clef" in caplog.text
    assert "RuntimeError" in caplog.text
    for forbidden in (sentinel, "private-token", ACCOUNT, "keep verbatim"):
        assert forbidden not in caplog.text
        assert forbidden not in repr(chain.diagnostics())
    assert chain.errors["clef"] == "transport_error"


def test_the_diagnostics_and_the_cli_surface_never_print_a_credential():
    chain = ProviderChain(Settings(jev_provider="clef"), CREDENTIALS, recorder([]))
    diagnostics = repr(chain.diagnostics())
    assert TOKEN_ENV in diagnostics and ACCOUNT_ENV in diagnostics
    assert "private-token" not in diagnostics
    assert ACCOUNT not in diagnostics


def test_the_endpoint_is_validated_like_every_other_provider():
    assert Settings().clef_base_url == "https://api.cloudflare.com/client/v4/accounts"
    assert Settings().clef_model == "clef"
    assert Settings(clef_base_url="https://clef-proxy.example").clef_base_url == (
        "https://clef-proxy.example"
    )
    with pytest.raises(ValueError):
        Settings(clef_base_url="http://192.168.1.10")
    with pytest.raises(ValueError):
        Settings(clef_base_url="https://user:pass@api.cloudflare.com")
    with pytest.raises(ValueError):
        Settings(clef_base_url="https://api.cloudflare.com/client/v4/accounts?a=b")


def test_a_clef_member_of_an_ordered_chain_still_needs_its_account():
    """Membership is decided on keys, so a missing account fails per request.

    The refusal is reported as ``401``, which is already a fallback trigger, so
    an ordered chain moves to its next member rather than stopping. No request
    is attempted for Clef either way.
    """
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        if "cloudflare" in url:
            raise AssertionError("no Clef request may be attempted")
        return {"answers": {q: {"noul": 0.4} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_fallback_order=("clef", "typesafe")),
        {"CLOUDFLARE_API_TOKEN": "private-token", "TYPESAFE_API_KEY": "private-one"},
        transport,
    )
    assert chain.order == ["clef", "typesafe"]
    assert chain.score({}, QUESTIONS) == {"probe:keep_result": 0.4}
    assert seen == ["https://api.typesafe.ai/v1/systemone"]
    assert chain.diagnostics()["last_errors"] == {"clef": "401"}
    assert chain.last_provider == "typesafe"
    # Pinning Clef with no account id fails at load instead, naming it, because
    # a pinned provider promises a usable route.
    with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
        ProviderChain(
            Settings(jev_provider="clef"), {"CLOUDFLARE_API_TOKEN": "private-token"}
        )
    assert seen == ["https://api.typesafe.ai/v1/systemone"]
