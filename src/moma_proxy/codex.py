"""Codex integration helpers for MOMA proxy."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROFILE = "moma"
DEFAULT_PROVIDER = "moma_proxy"
DEFAULT_MODEL = "ZHIPU/GLM-5.1"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_ENV_KEY = "MOMA_PROXY_API_KEY"


@dataclass(frozen=True)
class CodexInstallConfig:
    """Configuration for installing the Codex MOMA profile."""

    codex_home: Path
    profile: str = DEFAULT_PROFILE
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    env_key: str = DEFAULT_ENV_KEY

    @property
    def config_path(self) -> Path:
        return self.codex_home / "config.toml"

    @property
    def profile_path(self) -> Path:
        return self.codex_home / f"{self.profile}.config.toml"


def default_codex_home() -> Path:
    """Return Codex home, respecting CODEX_HOME when set."""
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _remove_toml_table(content: str, table_name: str) -> str:
    """Remove a top-level TOML table and its body."""
    lines = content.splitlines()
    output: list[str] = []
    target_header = f"[{table_name}]"
    in_target = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == target_header:
                in_target = True
                continue
            in_target = False

        if not in_target:
            output.append(line)

    return "\n".join(output).rstrip()


def _provider_block(config: CodexInstallConfig) -> str:
    return "\n".join(
        [
            f"[model_providers.{config.provider}]",
            'name = "MOMA Proxy"',
            f"base_url = {_toml_quote(config.base_url)}",
            f"env_key = {_toml_quote(config.env_key)}",
            'wire_api = "responses"',
        ]
    )


def _profile_content(config: CodexInstallConfig) -> str:
    return "\n".join(
        [
            f"model = {_toml_quote(config.model)}",
            f"model_provider = {_toml_quote(config.provider)}",
            "",
        ]
    )


def render_codex_config(existing_content: str, config: CodexInstallConfig) -> str:
    """Render config.toml with the managed MOMA provider table."""
    table_name = f"model_providers.{config.provider}"
    preserved = _remove_toml_table(existing_content, table_name)
    provider_block = _provider_block(config)
    if preserved:
        return f"{preserved}\n\n{provider_block}\n"
    return f"{provider_block}\n"


def install_codex_profile(config: CodexInstallConfig) -> tuple[Path, Path]:
    """Install or update Codex provider and profile files."""
    config.codex_home.mkdir(parents=True, exist_ok=True)

    existing = ""
    if config.config_path.exists():
        existing = config.config_path.read_text(encoding="utf-8")
    config.config_path.write_text(
        render_codex_config(existing, config),
        encoding="utf-8",
    )
    config.profile_path.write_text(_profile_content(config), encoding="utf-8")
    return config.config_path, config.profile_path


def run_codex_with_moma(
    profile: str = DEFAULT_PROFILE,
    env_key: str = DEFAULT_ENV_KEY,
    api_key: str = "dummy",
    argv: list[str] | None = None,
) -> int:
    """Run Codex with the MOMA profile and required client-side API key."""
    command = ["codex", "-p", profile]
    if argv:
        command.extend(argv)

    env = os.environ.copy()
    env.setdefault(env_key, api_key)

    try:
        completed = subprocess.run(command, env=env, check=False)
    except FileNotFoundError:
        print("Error: codex command not found in PATH", file=sys.stderr)
        return 127
    return completed.returncode
