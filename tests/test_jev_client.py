"""Decisions client: parsing, malformed payloads, redirect refusal."""

import pytest

from jev_lcm_hermes_compaction.jev_client import (
    NoRedirect,
    ProviderError,
    parse_answers,
)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"answers": {}},
        {"answers": {"x": {"noul": True}}},
        {"answers": {"x": {"noul": 2}}},
    ],
)
def test_malformed(data):
    with pytest.raises(ProviderError):
        parse_answers(data, ["x"])


def test_parse_and_redirection():
    assert parse_answers({"answers": {"x": {"noul": 0}}}, ["x"]) == {"x": 0.0}
    assert str(ProviderError("private-key-value")) == "transport_error"
    assert (
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere")
        is None
    )
