"""Test configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from moma_proxy.config import Config, ServerConfig, UpstreamConfig


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
    assert config.port == 8080


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


def test_config_file_not_found():
    """Test error when config file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        Config.from_file("/nonexistent/config.yaml")