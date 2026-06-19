"""Configuration handling for AgentBridge."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

ProviderApi = Literal["openai_chat", "openai_responses", "anthropic_messages"]
ClientProtocol = Literal["codex_responses", "anthropic"]
Mode = Literal["codex", "anthropic"]
ReasoningMode = Literal["passthrough", "thinking", "none"]

DEFAULT_MODEL = "ZHIPU/GLM-5.1"
DEFAULT_PORT = 17681
SUPPORTED_PROTOCOL_PAIRS: set[tuple[ClientProtocol, ProviderApi]] = {
    ("anthropic", "openai_chat"),
    ("codex_responses", "openai_chat"),
}

DEFAULT_CONFIG_FILENAME = "config.yaml"


def _find_config_near_package(filename: str | Path) -> Path | None:
    """Walk upward from the package directory to find a config file.

    This supports editable installs where config.yaml lives in the project
    root, which is an ancestor of the package source directory.
    """
    try:
        start = Path(__file__).resolve().parent
    except (ValueError, OSError):
        return None
    for parent in [start, *start.parents]:
        candidate = parent / filename
        if candidate.exists():
            return candidate
        # Stop at filesystem root – no need to walk the entire tree
        if parent == parent.parent:
            break
    return None


def resolve_config_path(path: str | Path | None = None) -> Path:
    """Resolve the configuration file path by searching known locations.

    Search order when *path* is ``None`` or a bare filename:
      1. The explicit *path* (if given and absolute, return immediately).
      2. Current working directory.
      3. Walk upward from the package directory (editable install support).
      4. ``~/.config/agent-bridge/config.yaml`` (XDG-style user config).
      5. The ``AGENT_BRIDGE_CONFIG`` environment variable.

    Returns the first existing path.  If none exists, returns the original
    *path* (or the CWD default) so that downstream code can raise a clear
    ``FileNotFoundError``.
    """
    if path is None:
        path = DEFAULT_CONFIG_FILENAME
    path = Path(path)

    # If the user gave an absolute path, respect it exactly.
    if path.is_absolute():
        return path

    # 1. Current working directory
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate

    # 2. Walk upward from the package directory (editable installs)
    pkg_candidate = _find_config_near_package(path)
    if pkg_candidate is not None:
        return pkg_candidate

    # 3. XDG-style user config directory
    xdg_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "agent-bridge"
    xdg_candidate = xdg_dir / path
    if xdg_candidate.exists():
        return xdg_candidate

    # 4. AGENT_BRIDGE_CONFIG environment variable
    env_path = os.environ.get("AGENT_BRIDGE_CONFIG")
    if env_path:
        env_candidate = Path(env_path)
        if env_candidate.exists():
            return env_candidate

    # Nothing found – return the CWD default so that the caller can raise
    # a clear error about the missing file.
    return cwd_candidate


@dataclass
class UpstreamConfig:
    """Upstream GLM platform configuration."""

    base_url: str
    api_key: str = ""

    def __post_init__(self) -> None:
        # Support environment variable expansion
        if self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var, "")


@dataclass
class ProviderConfig:
    """Model provider configuration."""

    base_url: str
    api_key: str = ""
    api_key_env: str | None = None
    model: str = DEFAULT_MODEL
    provider_api: ProviderApi = "openai_chat"
    client_protocol: ClientProtocol = "codex_responses"
    reasoning_mode: ReasoningMode = "passthrough"

    def __post_init__(self) -> None:
        if self.api_key_env and not self.api_key:
            self.api_key = os.environ.get(self.api_key_env, "")
        elif self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var, "")

    def to_upstream(self) -> UpstreamConfig:
        """Return the legacy upstream shape used by the server."""
        return UpstreamConfig(base_url=self.base_url, api_key=self.api_key)


@dataclass
class ServerConfig:
    """Server binding configuration."""

    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    """Main configuration."""

    upstream: UpstreamConfig | None = None
    server: ServerConfig = field(default_factory=ServerConfig)
    mode: Mode = "codex"
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    active_provider: str | None = None
    default_model: str = DEFAULT_MODEL

    def __post_init__(self) -> None:
        if self.upstream is None and self.providers:
            self.apply_provider(self.active_provider or next(iter(self.providers)))
        if self.upstream is None:
            raise ValueError("Either upstream or providers must be configured")

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        providers = {
            name: ProviderConfig(**provider_data)
            for name, provider_data in (data.get("providers") or {}).items()
        }
        upstream_data = data.get("upstream")
        upstream = UpstreamConfig(**upstream_data) if upstream_data else None

        config = cls(
            upstream=upstream,
            server=ServerConfig(**data.get("server", {})),
            mode=data.get("mode", "codex"),
            logging=LoggingConfig(**data.get("logging", {})),
            providers=providers,
            active_provider=data.get("active_provider"),
            default_model=data.get("default_model", DEFAULT_MODEL),
        )
        if providers and data.get("active_provider"):
            config.apply_provider(data["active_provider"])
        return config

    def get_provider(self, name: str | None = None) -> ProviderConfig:
        """Return a configured provider or a legacy provider from upstream."""
        provider_name = name or self.active_provider
        if provider_name is None and self.upstream is None and self.providers:
            provider_name = next(iter(self.providers))
        if provider_name:
            if provider_name == "moma" and not self.providers and self.upstream is not None:
                return ProviderConfig(
                    base_url=self.upstream.base_url,
                    api_key=self.upstream.api_key,
                    model=self.default_model,
                    client_protocol=(
                        "anthropic" if self.mode == "anthropic" else "codex_responses"
                    ),
                )
            try:
                return self.providers[provider_name]
            except KeyError as exc:
                raise ValueError(f"Unknown provider: {provider_name}") from exc

        if self.upstream is None:
            raise ValueError("No provider selected")

        return ProviderConfig(
            base_url=self.upstream.base_url,
            api_key=self.upstream.api_key,
            model=self.default_model,
            client_protocol="anthropic" if self.mode == "anthropic" else "codex_responses",
        )

    def apply_provider(
        self,
        name: str | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        model: str | None = None,
        provider_api: ProviderApi | None = None,
        client_protocol: ClientProtocol | None = None,
        reasoning_mode: ReasoningMode | None = None,
    ) -> ProviderConfig:
        """Select a provider and apply optional CLI overrides."""
        selected_name = name or self.active_provider
        if selected_name is None and not base_url and self.providers:
            selected_name = next(iter(self.providers))
        provider = (
            self.get_provider(selected_name)
            if selected_name or not base_url
            else ProviderConfig(base_url=base_url)
        )
        resolved_api_key = api_key if api_key is not None else provider.api_key
        if api_key_env is not None and api_key is None:
            resolved_api_key = ""
        provider = ProviderConfig(
            base_url=base_url or provider.base_url,
            api_key=resolved_api_key,
            api_key_env=api_key_env if api_key_env is not None else provider.api_key_env,
            model=model or provider.model,
            provider_api=provider_api or provider.provider_api,
            client_protocol=client_protocol or provider.client_protocol,
            reasoning_mode=reasoning_mode or provider.reasoning_mode,
        )
        validate_protocol_pair(provider.client_protocol, provider.provider_api)

        self.upstream = provider.to_upstream()
        self.default_model = provider.model
        self.mode = "anthropic" if provider.client_protocol == "anthropic" else "codex"
        if selected_name:
            self.active_provider = selected_name
        return provider


def validate_protocol_pair(client_protocol: ClientProtocol, provider_api: ProviderApi) -> None:
    """Reject protocol combinations that this codebase cannot serve yet."""
    pair = (client_protocol, provider_api)
    if pair not in SUPPORTED_PROTOCOL_PAIRS:
        supported = ", ".join(
            f"{client}->{provider}" for client, provider in sorted(SUPPORTED_PROTOCOL_PAIRS)
        )
        raise ValueError(
            f"Unsupported protocol combination: {client_protocol}->{provider_api}. "
            f"Supported: {supported}"
        )
