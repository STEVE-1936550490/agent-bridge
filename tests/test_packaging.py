"""Tests for package metadata that affects installed CLI commands."""

import tomllib
from pathlib import Path


def test_console_scripts_include_agent_bridge_and_legacy_commands() -> None:
    """AgentBridge is the public CLI while legacy entry points remain available."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    scripts = pyproject["project"]["scripts"]

    assert scripts["agent-bridge"] == "moma_proxy.main:main"
    assert scripts["moma-proxy"] == "moma_proxy.main:main"
    assert scripts["moma"] == "moma_proxy.codex_cli:main"
