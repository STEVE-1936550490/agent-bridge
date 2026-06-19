"""Cross-platform installation helpers for MOMA proxy."""

from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .codex import CodexInstallConfig, install_codex_profile

DEFAULT_NPM_REGISTRY = "https://registry.npmmirror.com"
CODEX_CLI_PACKAGE = "@openai/codex"
CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"


@dataclass(frozen=True)
class ToolStatus:
    """Detected command availability."""

    name: str
    command: str
    path: str | None

    @property
    def available(self) -> bool:
        return self.path is not None


@dataclass(frozen=True)
class InstallSummary:
    """Result of the local setup command."""

    platform_name: str
    python_executable: str
    python_version: str
    package_version: str
    config_path: Path
    config_created: bool
    codex_config_path: Path | None
    codex_profile_path: Path | None
    codex_cli_installed: bool
    claude_code_installed: bool
    npm_registry: str
    tools: list[ToolStatus]


def package_version() -> str:
    """Return the installed package version when available."""
    try:
        return importlib.metadata.version("agent-bridge")
    except importlib.metadata.PackageNotFoundError:
        try:
            return importlib.metadata.version("moma-proxy")
        except importlib.metadata.PackageNotFoundError:
            return "editable/local"


def detect_tools() -> list[ToolStatus]:
    """Detect optional external tools used by this project."""
    return [
        ToolStatus("Node.js", "node", shutil.which("node")),
        ToolStatus("npm", "npm", shutil.which("npm")),
        ToolStatus("Codex CLI", "codex", shutil.which("codex")),
        ToolStatus("Claude Code", "claude", shutil.which("claude")),
    ]


def ensure_config_file(config_path: Path, template_path: Path) -> bool:
    """Create config from template if missing, without overwriting user config."""
    if config_path.exists():
        return False
    if not template_path.exists():
        raise FileNotFoundError(f"Config template not found: {template_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path, config_path)
    return True


def install_npm_global_package(
    package: str,
    *,
    npm_command: str = "npm",
    registry: str = DEFAULT_NPM_REGISTRY,
) -> bool:
    """Install a global npm package and return whether the command succeeded."""
    completed = subprocess.run(
        [npm_command, "install", "-g", package, "--registry", registry],
        check=False,
    )
    return completed.returncode == 0


def run_local_install(
    *,
    config_path: Path,
    template_path: Path,
    codex_install_config: CodexInstallConfig,
    install_codex_cli: bool = False,
    install_claude_code: bool = False,
    install_codex_profile_enabled: bool = True,
    npm_registry: str = DEFAULT_NPM_REGISTRY,
) -> InstallSummary:
    """Run the cross-platform local setup flow."""
    tools = detect_tools()
    npm = next((tool for tool in tools if tool.command == "npm"), None)
    codex = next((tool for tool in tools if tool.command == "codex"), None)
    claude = next((tool for tool in tools if tool.command == "claude"), None)

    codex_cli_installed = False
    if install_codex_cli and codex is not None and not codex.available:
        if npm is None or not npm.available:
            raise RuntimeError("Cannot install Codex CLI because npm was not found in PATH")
        codex_cli_installed = install_npm_global_package(
            CODEX_CLI_PACKAGE,
            npm_command=npm.path,
            registry=npm_registry,
        )
        tools = detect_tools()

    claude_code_installed = False
    if install_claude_code and claude is not None and not claude.available:
        if npm is None or not npm.available:
            raise RuntimeError("Cannot install Claude Code because npm was not found in PATH")
        claude_code_installed = install_npm_global_package(
            CLAUDE_CODE_PACKAGE,
            npm_command=npm.path,
            registry=npm_registry,
        )
        tools = detect_tools()

    config_created = ensure_config_file(config_path, template_path)

    codex_config_path: Path | None = None
    codex_profile_path: Path | None = None
    if install_codex_profile_enabled:
        codex_config_path, codex_profile_path = install_codex_profile(codex_install_config)

    return InstallSummary(
        platform_name=platform.system() or sys.platform,
        python_executable=sys.executable,
        python_version=platform.python_version(),
        package_version=package_version(),
        config_path=config_path,
        config_created=config_created,
        codex_config_path=codex_config_path,
        codex_profile_path=codex_profile_path,
        codex_cli_installed=codex_cli_installed,
        claude_code_installed=claude_code_installed,
        npm_registry=npm_registry,
        tools=tools,
    )


def format_install_summary(summary: InstallSummary) -> str:
    """Render a user-facing install summary."""
    lines = [
        "AgentBridge setup summary",
        f"- Platform: {summary.platform_name}",
        f"- Python: {summary.python_version} ({summary.python_executable})",
        f"- Package: agent-bridge {summary.package_version}",
        f"- npm registry: {summary.npm_registry}",
    ]

    if summary.config_created:
        lines.append(f"- Config: created {summary.config_path}")
    else:
        lines.append(f"- Config: kept existing {summary.config_path}")

    if summary.codex_config_path and summary.codex_profile_path:
        lines.append(f"- Codex provider: updated {summary.codex_config_path}")
        lines.append(f"- Codex profile: updated {summary.codex_profile_path}")

    if summary.codex_cli_installed:
        lines.append("- Codex CLI: installed with npm")
    if summary.claude_code_installed:
        lines.append("- Claude Code: installed with npm")

    lines.append("- Tool detection:")
    for tool in summary.tools:
        status = tool.path if tool.path else "missing"
        lines.append(f"  - {tool.name} ({tool.command}): {status}")

    missing = {tool.command for tool in summary.tools if not tool.available}
    if "codex" in missing:
        lines.append(
            "- Next: install Codex CLI with "
            f"`npm install -g {CODEX_CLI_PACKAGE} --registry {summary.npm_registry}` "
            "or rerun with `--install-codex-cli`."
        )
    if "claude" in missing:
        lines.append(
            "- Next: install Claude Code CLI for the supported `/v1/messages` "
            f"compatibility path with `npm install -g {CLAUDE_CODE_PACKAGE} "
            f"--registry {summary.npm_registry}` or rerun with `--install-claude-code`."
        )
    lines.append(
        "- Default Codex remains unchanged; use `codex -p agent_bridge` "
        "or `agent-bridge start` for AgentBridge."
    )
    return "\n".join(lines)
