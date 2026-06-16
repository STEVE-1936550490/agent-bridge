"""Tests for Codex integration helpers."""

import os
from pathlib import Path
from unittest.mock import patch

from moma_proxy.codex import (
    CodexInstallConfig,
    install_codex_profile,
    render_codex_config,
    run_codex_with_moma,
)
from moma_proxy.main import main


def test_render_codex_config_preserves_default_model() -> None:
    """Installing the MOMA provider must not change the default Codex model."""
    existing = """
model = "gpt-5.5"
model_provider = "openai"

[model_providers.openai]
name = "OpenAI"
""".strip()
    config = CodexInstallConfig(
        codex_home=Path("/tmp/codex"),
        provider="moma_proxy",
        base_url="http://127.0.0.1:8080/v1",
    )

    rendered = render_codex_config(existing, config)

    assert 'model = "gpt-5.5"' in rendered
    assert 'model_provider = "openai"' in rendered
    assert "[model_providers.openai]" in rendered
    assert "[model_providers.moma_proxy]" in rendered
    assert 'wire_api = "responses"' in rendered


def test_render_codex_config_replaces_existing_provider() -> None:
    """Reinstalling should update the managed provider instead of duplicating it."""
    existing = """
model = "gpt-5.5"

[model_providers.moma_proxy]
name = "Old"
base_url = "http://old.example/v1"

[model_providers.other]
name = "Other"
""".strip()
    config = CodexInstallConfig(
        codex_home=Path("/tmp/codex"),
        provider="moma_proxy",
        base_url="http://127.0.0.1:9000/v1",
    )

    rendered = render_codex_config(existing, config)

    assert rendered.count("[model_providers.moma_proxy]") == 1
    assert "http://old.example/v1" not in rendered
    assert 'base_url = "http://127.0.0.1:9000/v1"' in rendered
    assert "[model_providers.other]" in rendered


def test_install_codex_profile_writes_config_and_profile(tmp_path: Path) -> None:
    """Install writes both the provider block and profile file."""
    (tmp_path / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    config = CodexInstallConfig(codex_home=tmp_path)

    config_path, profile_path = install_codex_profile(config)

    assert config_path == tmp_path / "config.toml"
    assert profile_path == tmp_path / "moma.config.toml"
    assert "[model_providers.moma_proxy]" in config_path.read_text(encoding="utf-8")
    assert 'model = "ZHIPU/GLM-5.1"' in profile_path.read_text(encoding="utf-8")


def test_main_install_codex_uses_codex_home(tmp_path: Path) -> None:
    """CLI install-codex supports an explicit Codex home for tests and users."""
    result = main(["install-codex", "--codex-home", str(tmp_path)])

    assert result == 0
    assert (tmp_path / "config.toml").exists()
    assert (tmp_path / "moma.config.toml").exists()


def test_run_codex_with_moma_injects_env_key() -> None:
    """The MOMA launcher sets Codex's required client-side API key."""
    captured = {}

    def fake_run(command, env, check):
        captured["command"] = command
        captured["env"] = env
        captured["check"] = check

        class Completed:
            returncode = 0

        return Completed()

    with patch.dict(os.environ, {}, clear=True):
        with patch("moma_proxy.codex.subprocess.run", fake_run):
            result = run_codex_with_moma(argv=["exec", "hello"])

    assert result == 0
    assert captured["command"] == ["codex", "-p", "moma", "exec", "hello"]
    assert captured["env"]["MOMA_PROXY_API_KEY"] == "dummy"
    assert captured["check"] is False
