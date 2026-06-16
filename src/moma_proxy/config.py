"""Configuration handling for MOMA proxy."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


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
class ServerConfig:
    """Server binding configuration."""

    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    """Main configuration."""

    upstream: UpstreamConfig
    server: ServerConfig = field(default_factory=ServerConfig)
    mode: Literal["codex", "anthropic"] = "codex"
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls(
            upstream=UpstreamConfig(**data["upstream"]),
            server=ServerConfig(**data.get("server", {})),
            mode=data.get("mode", "codex"),
            logging=LoggingConfig(**data.get("logging", {})),
        )