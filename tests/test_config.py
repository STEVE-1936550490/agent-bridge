"""Test configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from moma_proxy.config import Config, ProviderConfig, ServerConfig, UpstreamConfig


def test_upstream_config_env_expansion():
    """Test API key expansion from environment variable."""
    os.environ["TEST_API_KEY"] = "test_key_value"
    config = UpstreamConfig(base_url="https://api.example.com", api_key="${TEST_API_KEY}")
    assert config.api_key == "test_key_value"
    del os.environ["TEST_API_KEY"]


def test_upstream_config_env_missing():
    """Test API key when env var is missing."""
    config = UpstreamConfig(base_url="https://api.example.com", api_key="${MISSING_KEY}")
    assert config.api_key == ""


def test_server_config_defaults():
    """Test server config default values."""
    config = ServerConfig()
    assert config.host == "0.0.0.0"
    assert config.port == 17681


def test_config_from_file():
    """Test loading config from YAML file."""
    yaml_content = """
upstream:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
server:
  host: "127.0.0.1"
  port: 9000
mode: "codex"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = Config.from_file(f.name)
        assert config.upstream.base_url == "https://api.example.com/v1"
        assert config.upstream.api_key == "test-key"
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 9000
        assert config.mode == "codex"
        Path(f.name).unlink()


def test_provider_config_env_expansion() -> None:
    """Provider config can resolve API keys from an env var name."""
    os.environ["PROVIDER_TEST_KEY"] = "provider-key"
    config = ProviderConfig(
        base_url="https://api.example.com/v1",
        api_key_env="PROVIDER_TEST_KEY",
    )
    assert config.api_key == "provider-key"
    del os.environ["PROVIDER_TEST_KEY"]


def test_config_from_file_with_active_provider() -> None:
    """Provider-aware config selects the active provider."""
    yaml_content = """
active_provider: "moma"
providers:
  moma:
    base_url: "https://moma.example.com/v1"
    api_key: "moma-key"
    model: "ZHIPU/GLM-5.1"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"
  local:
    base_url: "http://127.0.0.1:8000/v1"
    api_key: "local-key"
    model: "local-model"
    provider_api: "openai_chat"
    client_protocol: "codex_responses"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = Config.from_file(f.name)
        assert config.active_provider == "moma"
        assert config.upstream is not None
        assert config.upstream.base_url == "https://moma.example.com/v1"
        assert config.upstream.api_key == "moma-key"
        assert config.default_model == "ZHIPU/GLM-5.1"
        Path(f.name).unlink()


def test_apply_provider_switches_provider() -> None:
    """A configured provider can be selected by name."""
    config = Config(
        providers={
            "moma": ProviderConfig(base_url="https://moma.example.com/v1", api_key="moma"),
            "local": ProviderConfig(
                base_url="http://127.0.0.1:8000/v1",
                api_key="local",
                model="local-model",
            ),
        }
    )

    config.apply_provider("local")

    assert config.active_provider == "local"
    assert config.upstream is not None
    assert config.upstream.base_url == "http://127.0.0.1:8000/v1"
    assert config.upstream.api_key == "local"
    assert config.default_model == "local-model"


def test_apply_moma_provider_uses_legacy_upstream_when_no_providers() -> None:
    """Legacy configs can still use -p moma during the provider transition."""
    config = Config(
        upstream=UpstreamConfig(
            base_url="https://moma.example.com/v1",
            api_key="legacy-key",
        )
    )

    provider = config.apply_provider("moma")

    assert provider.base_url == "https://moma.example.com/v1"
    assert provider.api_key == "legacy-key"
    assert config.active_provider == "moma"
    assert config.upstream is not None
    assert config.upstream.base_url == "https://moma.example.com/v1"


def test_apply_provider_supports_temporary_overrides() -> None:
    """CLI-style overrides can create an ad hoc OpenAI-compatible provider."""
    os.environ["TEMP_PROVIDER_KEY"] = "temp-key"
    config = Config(upstream=UpstreamConfig(base_url="https://moma.example.com/v1"))

    provider = config.apply_provider(
        base_url="http://127.0.0.1:8000/v1",
        api_key_env="TEMP_PROVIDER_KEY",
        model="custom-model",
        provider_api="openai_chat",
        client_protocol="codex_responses",
    )

    assert provider.api_key == "temp-key"
    assert config.upstream is not None
    assert config.upstream.base_url == "http://127.0.0.1:8000/v1"
    assert config.default_model == "custom-model"
    del os.environ["TEMP_PROVIDER_KEY"]


def test_apply_provider_rejects_unsupported_protocol_pair() -> None:
    """Unsupported client/provider protocol pairs fail before server startup."""
    config = Config(upstream=UpstreamConfig(base_url="https://moma.example.com/v1"))

    with pytest.raises(ValueError, match="Unsupported protocol combination"):
        config.apply_provider(
            provider_api="anthropic_messages",
            client_protocol="codex_responses",
        )


def test_config_file_not_found():
    """Test error when config file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        Config.from_file("/nonexistent/config.yaml")
