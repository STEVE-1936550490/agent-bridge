"""Interactive and scripted configuration helpers."""

from __future__ import annotations

import getpass
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from .config import ClientProtocol, ProviderApi

DEFAULT_PROVIDER_NAME = "moma"
DEFAULT_BASE_URL = "https://moma.cmecloud.cn/v1"
DEFAULT_API_KEY_ENV = "MOMA_API_KEY"
DEFAULT_MODEL = "ZHIPU/GLM-5.1"
DEFAULT_PROVIDER_API: ProviderApi = "openai_chat"
DEFAULT_CLIENT_PROTOCOL: ClientProtocol = "codex_responses"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 17681


@dataclass(frozen=True)
class ConfigureOptions:
    """Options for writing one provider config."""

    config_path: Path
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    provider_api: ProviderApi | None = None
    client_protocol: ClientProtocol | None = None
    host: str | None = None
    port: int | None = None
    interactive: bool = True


@dataclass(frozen=True)
class ConfigureSummary:
    """Result of updating config."""

    config_path: Path
    provider: str
    base_url: str
    model: str
    provider_api: str
    client_protocol: str
    host: str
    port: int
    api_key_source: str


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML object")
    return data


def _prompt(
    prompt: str,
    default: str,
    input_func: Callable[[str], str],
) -> str:
    suffix = f" [{default}]" if default else ""
    value = input_func(f"{prompt}{suffix}: ").strip()
    return value or default


def _existing_provider(data: dict, name: str) -> dict:
    providers = data.get("providers")
    if isinstance(providers, dict):
        provider = providers.get(name)
        if isinstance(provider, dict):
            return provider
    return {}


def _legacy_upstream(data: dict) -> dict:
    upstream = data.get("upstream")
    return upstream if isinstance(upstream, dict) else {}


def configure_provider(
    options: ConfigureOptions,
    *,
    input_func: Callable[[str], str] = input,
    secret_func: Callable[[str], str] = getpass.getpass,
) -> ConfigureSummary:
    """Create or update a provider in config.yaml."""
    data = _load_yaml(options.config_path)
    active_provider = data.get("active_provider")
    provider_name = options.provider or (
        str(active_provider) if active_provider else DEFAULT_PROVIDER_NAME
    )
    existing = _existing_provider(data, provider_name)
    legacy = _legacy_upstream(data)

    default_base_url = str(existing.get("base_url") or legacy.get("base_url") or DEFAULT_BASE_URL)
    default_api_key_env = str(existing.get("api_key_env") or DEFAULT_API_KEY_ENV)
    default_model = str(existing.get("model") or data.get("default_model") or DEFAULT_MODEL)
    default_provider_api = str(existing.get("provider_api") or DEFAULT_PROVIDER_API)
    default_client_protocol = str(existing.get("client_protocol") or DEFAULT_CLIENT_PROTOCOL)
    server = data.get("server") if isinstance(data.get("server"), dict) else {}
    default_host = str(server.get("host") or DEFAULT_HOST)
    default_port = int(server.get("port") or DEFAULT_PORT)

    api_key = options.api_key
    api_key_env = options.api_key_env
    if options.interactive:
        provider_name = _prompt("Provider name", provider_name, input_func)
        default_base_url = _prompt(
            "Provider base URL", options.base_url or default_base_url, input_func
        )
        default_model = _prompt("Default model", options.model or default_model, input_func)
        default_provider_api = _prompt(
            "Provider API protocol",
            options.provider_api or default_provider_api,
            input_func,
        )
        default_client_protocol = _prompt(
            "Client protocol",
            options.client_protocol or default_client_protocol,
            input_func,
        )
        api_key_env = _prompt(
            "API key environment variable", api_key_env or default_api_key_env, input_func
        )
        direct_key = secret_func("Direct API key (optional, blank to use env var): ").strip()
        api_key = direct_key or api_key
        default_host = _prompt("Server host", options.host or default_host, input_func)
        default_port = int(_prompt("Server port", str(options.port or default_port), input_func))

    base_url = options.base_url or default_base_url
    model = options.model or default_model
    provider_api = options.provider_api or default_provider_api
    client_protocol = options.client_protocol or default_client_protocol
    host = options.host or default_host
    port = options.port or default_port

    provider_data = {
        "base_url": base_url,
        "model": model,
        "provider_api": provider_api,
        "client_protocol": client_protocol,
    }
    if api_key:
        provider_data["api_key"] = api_key
    elif api_key_env:
        provider_data["api_key_env"] = api_key_env
    elif existing.get("api_key"):
        provider_data["api_key"] = existing["api_key"]

    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    providers[provider_name] = provider_data

    data["active_provider"] = provider_name
    data["default_model"] = model
    data["providers"] = providers
    data["server"] = {"host": host, "port": port}
    data["mode"] = "anthropic" if client_protocol == "anthropic" else "codex"
    data.setdefault(
        "logging",
        {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    )

    data["upstream"] = {
        "base_url": base_url,
        "api_key": api_key if api_key else f"${{{api_key_env or DEFAULT_API_KEY_ENV}}}",
    }

    options.config_path.parent.mkdir(parents=True, exist_ok=True)
    with options.config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=False)

    return ConfigureSummary(
        config_path=options.config_path,
        provider=provider_name,
        base_url=base_url,
        model=model,
        provider_api=str(provider_api),
        client_protocol=str(client_protocol),
        host=host,
        port=port,
        api_key_source="direct" if api_key else f"env:{api_key_env or DEFAULT_API_KEY_ENV}",
    )


def format_configure_summary(summary: ConfigureSummary) -> str:
    """Render a concise configuration summary."""
    return "\n".join(
        [
            "AgentBridge config updated",
            f"- Config: {summary.config_path}",
            f"- Provider: {summary.provider}",
            f"- Base URL: {summary.base_url}",
            f"- Model: {summary.model}",
            f"- Provider API: {summary.provider_api}",
            f"- Client protocol: {summary.client_protocol}",
            f"- Server: {summary.host}:{summary.port}",
            f"- API key: {summary.api_key_source}",
        ]
    )
