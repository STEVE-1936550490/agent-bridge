"""Tests for interactive provider configuration."""

from pathlib import Path

import yaml

from moma_proxy.configure import ConfigureOptions, configure_provider
from moma_proxy.main import main


def test_configure_provider_writes_provider_config_from_flags(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    summary = configure_provider(
        ConfigureOptions(
            config_path=config_path,
            provider="local",
            base_url="http://127.0.0.1:8000/v1",
            api_key_env="LOCAL_API_KEY",
            model="local-model",
            provider_api="openai_chat",
            client_protocol="codex_responses",
            host="127.0.0.1",
            port=19000,
            interactive=False,
        )
    )

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert summary.provider == "local"
    assert data["active_provider"] == "local"
    assert data["default_model"] == "local-model"
    assert data["providers"]["local"] == {
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key_env": "LOCAL_API_KEY",
        "model": "local-model",
        "provider_api": "openai_chat",
        "client_protocol": "codex_responses",
    }
    assert data["upstream"] == {
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key": "${LOCAL_API_KEY}",
    }
    assert data["server"] == {"host": "127.0.0.1", "port": 19000}


def test_main_configure_no_interactive(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"

    result = main(
        [
            "configure",
            "--config",
            str(config_path),
            "--codex-home",
            str(codex_home),
            "--provider",
            "moma",
            "--base-url",
            "https://moma.example.com/v1",
            "--api-key-env",
            "MOMA_API_KEY",
            "--model",
            "ZHIPU/GLM-5.1",
            "--provider-api",
            "openai_chat",
            "--client-protocol",
            "codex_responses",
            "--no-interactive",
        ]
    )

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert result == 0
    assert data["providers"]["moma"]["base_url"] == "https://moma.example.com/v1"
    assert data["providers"]["moma"]["api_key_env"] == "MOMA_API_KEY"
    assert (codex_home / "config.toml").exists()
    assert (codex_home / "moma.config.toml").exists()


def test_main_configure_syncs_codex_profile_to_local_proxy(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"

    result = main(
        [
            "configure",
            "--config",
            str(config_path),
            "--codex-home",
            str(codex_home),
            "--provider",
            "local",
            "--base-url",
            "https://provider.example.com/v1",
            "--api-key-env",
            "LOCAL_API_KEY",
            "--model",
            "local-model",
            "--provider-api",
            "openai_chat",
            "--client-protocol",
            "codex_responses",
            "--host",
            "0.0.0.0",
            "--port",
            "19001",
            "--no-interactive",
        ]
    )

    codex_config = (codex_home / "config.toml").read_text(encoding="utf-8")
    codex_profile = (codex_home / "moma.config.toml").read_text(encoding="utf-8")
    assert result == 0
    assert 'base_url = "http://127.0.0.1:19001/v1"' in codex_config
    assert 'env_key = "MOMA_PROXY_API_KEY"' in codex_config
    assert 'model = "local-model"' in codex_profile


def test_main_configure_can_skip_codex_profile_sync(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"

    result = main(
        [
            "configure",
            "--config",
            str(config_path),
            "--codex-home",
            str(codex_home),
            "--provider",
            "local",
            "--base-url",
            "https://provider.example.com/v1",
            "--api-key-env",
            "LOCAL_API_KEY",
            "--model",
            "local-model",
            "--provider-api",
            "openai_chat",
            "--client-protocol",
            "codex_responses",
            "--skip-codex-profile",
            "--no-interactive",
        ]
    )

    assert result == 0
    assert not (codex_home / "config.toml").exists()


def test_configure_provider_interactive_uses_prompts(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    answers = iter(
        [
            "custom",
            "https://api.example.com/v1",
            "custom-model",
            "openai_chat",
            "codex_responses",
            "CUSTOM_API_KEY",
            "127.0.0.1",
            "18000",
        ]
    )

    summary = configure_provider(
        ConfigureOptions(config_path=config_path),
        input_func=lambda prompt: next(answers),
        secret_func=lambda prompt: "",
    )

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert summary.provider == "custom"
    assert data["providers"]["custom"]["api_key_env"] == "CUSTOM_API_KEY"
    assert data["server"]["port"] == 18000
