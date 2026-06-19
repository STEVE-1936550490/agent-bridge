"""Tests for observability compatibility helpers."""

import importlib

from aiohttp import web

import agent_bridge.observability as observability


def test_observability_falls_back_when_request_key_is_unavailable(monkeypatch) -> None:
    with monkeypatch.context() as patch:
        patch.delattr(web, "RequestKey", raising=False)
        reloaded = importlib.reload(observability)

        assert reloaded.REQ_MODEL == "model"
        assert reloaded.REQ_CLIENT_PROTOCOL == "client_protocol"

    importlib.reload(observability)


def test_token_usage_from_openai_fields() -> None:
    from agent_bridge.observability import TokenUsage

    usage = TokenUsage.from_usage_dict(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    )
    assert usage.source == "upstream"
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5
    assert usage.total_tokens == 15


def test_token_usage_from_anthropic_fields() -> None:
    from agent_bridge.observability import TokenUsage

    usage = TokenUsage.from_usage_dict({"input_tokens": 7, "output_tokens": 4})
    assert usage.source == "upstream"
    assert usage.input_tokens == 7
    assert usage.output_tokens == 4
    assert usage.total_tokens is None


def test_token_usage_from_non_dict_stays_unavailable() -> None:
    from agent_bridge.observability import TokenUsage

    assert TokenUsage.from_usage_dict(None).source == "unavailable"
    assert TokenUsage.from_usage_dict("not a dict").source == "unavailable"


def test_token_usage_from_empty_dict_stays_unavailable() -> None:
    from agent_bridge.observability import TokenUsage

    assert TokenUsage.from_usage_dict({}).source == "unavailable"


def test_token_usage_from_string_values_coerces() -> None:
    from agent_bridge.observability import TokenUsage

    usage = TokenUsage.from_usage_dict({"prompt_tokens": "12", "completion_tokens": "8"})
    assert usage.source == "upstream"
    assert usage.input_tokens == 12
    assert usage.output_tokens == 8
