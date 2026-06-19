"""Tests for Codex integration helpers."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from agent_bridge.codex import (
    DEFAULT_BASE_URL,
    CodexInstallConfig,
    install_codex_profile,
    render_codex_config,
    run_codex_with_agent_bridge,
)
from agent_bridge.main import main


def test_default_codex_base_url_uses_agentbridge_port() -> None:
    assert DEFAULT_BASE_URL == "http://127.0.0.1:17681/v1"


def test_render_codex_config_preserves_default_model() -> None:
    """Installing the AgentBridge provider must not change the default Codex model."""
    existing = """
model = "gpt-5.5"
model_provider = "openai"

[model_providers.openai]
name = "OpenAI"
""".strip()
    config = CodexInstallConfig(
        codex_home=Path("/tmp/codex"),
        provider="agent_bridge",
        base_url="http://127.0.0.1:17681/v1",
    )

    rendered = render_codex_config(existing, config)

    assert 'model = "gpt-5.5"' in rendered
    assert 'model_provider = "openai"' in rendered
    assert "[model_providers.openai]" in rendered
    assert "[model_providers.agent_bridge]" in rendered
    assert 'wire_api = "responses"' in rendered


def test_render_codex_config_replaces_existing_provider() -> None:
    """Reinstalling should update the managed provider instead of duplicating it."""
    existing = """
model = "gpt-5.5"

[model_providers.agent_bridge]
name = "Old"
base_url = "http://old.example/v1"

[model_providers.other]
name = "Other"
""".strip()
    config = CodexInstallConfig(
        codex_home=Path("/tmp/codex"),
        provider="agent_bridge",
        base_url="http://127.0.0.1:9000/v1",
    )

    rendered = render_codex_config(existing, config)

    assert rendered.count("[model_providers.agent_bridge]") == 1
    assert "http://old.example/v1" not in rendered
    assert 'base_url = "http://127.0.0.1:9000/v1"' in rendered
    assert "[model_providers.other]" in rendered


def test_install_codex_profile_writes_config_and_profile(tmp_path: Path) -> None:
    """Install writes both the provider block and profile file."""
    (tmp_path / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    config = CodexInstallConfig(codex_home=tmp_path)

    config_path, profile_path = install_codex_profile(config)

    assert config_path == tmp_path / "config.toml"
    assert profile_path == tmp_path / "agent_bridge.config.toml"
    assert "[model_providers.agent_bridge]" in config_path.read_text(encoding="utf-8")
    assert 'model = "ZHIPU/GLM-5.1"' in profile_path.read_text(encoding="utf-8")


def test_main_install_codex_uses_codex_home(tmp_path: Path) -> None:
    """CLI install-codex supports an explicit Codex home for tests and users."""
    result = main(["install-codex", "--codex-home", str(tmp_path)])

    assert result == 0
    assert (tmp_path / "config.toml").exists()
    assert (tmp_path / "agent_bridge.config.toml").exists()


def test_main_serve_rejects_unsupported_protocol_pair(tmp_path: Path) -> None:
    """CLI validates provider/client protocols before starting the server."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
upstream:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
""",
        encoding="utf-8",
    )

    result = main(
        [
            "serve",
            "--config",
            str(config_path),
            "--provider-api",
            "anthropic_messages",
            "--client-protocol",
            "codex_responses",
        ]
    )

    assert result == 1


def test_python_module_entrypoint_propagates_exit_code(tmp_path: Path) -> None:
    """python -m agent_bridge should return the main() exit code."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
upstream:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_bridge",
            "serve",
            "--config",
            str(config_path),
            "--provider-api",
            "anthropic_messages",
            "--client-protocol",
            "codex_responses",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "Unsupported protocol combination" in completed.stderr


def test_run_codex_with_agent_bridge_injects_env_key() -> None:
    """The compatibility launcher sets Codex's required client-side API key."""
    captured = {}

    def fake_run(command, env, check):
        captured["command"] = command
        captured["env"] = env
        captured["check"] = check

        class Completed:
            returncode = 0

        return Completed()

    with patch.dict(os.environ, {}, clear=True):
        with patch("agent_bridge.codex.subprocess.run", fake_run):
            result = run_codex_with_agent_bridge(argv=["exec", "hello"])

    assert result == 0
    assert captured["command"] == ["codex", "-p", "agent_bridge", "exec", "hello"]
    assert captured["env"]["AGENT_BRIDGE_API_KEY"] == "dummy"
    assert captured["check"] is False
