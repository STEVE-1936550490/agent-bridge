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
