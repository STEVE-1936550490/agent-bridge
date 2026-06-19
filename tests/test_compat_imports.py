"""Compatibility tests for the old moma_proxy package name."""

import importlib


def test_old_moma_proxy_import_aliases_agent_bridge() -> None:
    old_config = importlib.import_module("moma_proxy.config")
    new_config = importlib.import_module("agent_bridge.config")

    assert old_config.Config is new_config.Config
