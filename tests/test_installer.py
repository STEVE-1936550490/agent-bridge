"""Tests for cross-platform installer helpers."""

from pathlib import Path
from unittest.mock import patch

from moma_proxy.codex import CodexInstallConfig
from moma_proxy.installer import (
    ToolStatus,
    ensure_config_file,
    format_install_summary,
    run_local_install,
)
from moma_proxy.main import main


def test_ensure_config_file_creates_from_template(tmp_path: Path) -> None:
    template = tmp_path / "config.yaml.example"
    config = tmp_path / "config.yaml"
    template.write_text("upstream:\n  api_key: ${MOMA_API_KEY}\n", encoding="utf-8")

    created = ensure_config_file(config, template)

    assert created is True
    assert config.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")


def test_ensure_config_file_does_not_overwrite_existing_config(tmp_path: Path) -> None:
    template = tmp_path / "config.yaml.example"
    config = tmp_path / "config.yaml"
    template.write_text("template", encoding="utf-8")
    config.write_text("real-secret-config", encoding="utf-8")

    created = ensure_config_file(config, template)

    assert created is False
    assert config.read_text(encoding="utf-8") == "real-secret-config"


def test_main_install_creates_config_and_codex_profile(tmp_path: Path) -> None:
    template = tmp_path / "config.yaml.example"
    config = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"
    template.write_text("upstream:\n  api_key: ${MOMA_API_KEY}\n", encoding="utf-8")

    result = main(
        [
            "install",
            "--config",
            str(config),
            "--template",
            str(template),
            "--codex-home",
            str(codex_home),
        ]
    )

    assert result == 0
    assert config.exists()
    assert (codex_home / "config.toml").exists()
    assert (codex_home / "moma.config.toml").exists()


def test_run_local_install_can_install_codex_cli_with_npm(tmp_path: Path) -> None:
    template = tmp_path / "config.yaml.example"
    config = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"
    template.write_text("upstream:\n  api_key: ${MOMA_API_KEY}\n", encoding="utf-8")

    def fake_which(command: str) -> str | None:
        return "/usr/bin/npm" if command == "npm" else None

    class Completed:
        returncode = 0

    with patch("moma_proxy.installer.shutil.which", fake_which):
        with patch("moma_proxy.installer.subprocess.run", return_value=Completed()) as run:
            summary = run_local_install(
                config_path=config,
                template_path=template,
                codex_install_config=CodexInstallConfig(codex_home=codex_home),
                install_codex_cli=True,
            )

    assert summary.codex_cli_installed is True
    run.assert_called_once_with(
        [
            "/usr/bin/npm",
            "install",
            "-g",
            "@openai/codex",
            "--registry",
            "https://registry.npmmirror.com",
        ],
        check=False,
    )


def test_run_local_install_can_install_claude_code_with_npm(tmp_path: Path) -> None:
    template = tmp_path / "config.yaml.example"
    config = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"
    template.write_text("upstream:\n  api_key: ${MOMA_API_KEY}\n", encoding="utf-8")

    def fake_which(command: str) -> str | None:
        return "/usr/bin/npm" if command == "npm" else None

    class Completed:
        returncode = 0

    with patch("moma_proxy.installer.shutil.which", fake_which):
        with patch("moma_proxy.installer.subprocess.run", return_value=Completed()) as run:
            summary = run_local_install(
                config_path=config,
                template_path=template,
                codex_install_config=CodexInstallConfig(codex_home=codex_home),
                install_claude_code=True,
                npm_registry="https://registry.npmjs.org",
            )

    assert summary.claude_code_installed is True
    run.assert_called_once_with(
        [
            "/usr/bin/npm",
            "install",
            "-g",
            "@anthropic-ai/claude-code",
            "--registry",
            "https://registry.npmjs.org",
        ],
        check=False,
    )


def test_format_install_summary_reports_missing_codex_and_claude(tmp_path: Path) -> None:
    template = tmp_path / "config.yaml.example"
    config = tmp_path / "config.yaml"
    codex_home = tmp_path / "codex"
    template.write_text("upstream:\n  api_key: ${MOMA_API_KEY}\n", encoding="utf-8")

    with patch("moma_proxy.installer.detect_tools") as detect:
        detect.return_value = [
            ToolStatus("Node.js", "node", "/usr/bin/node"),
            ToolStatus("npm", "npm", "/usr/bin/npm"),
            ToolStatus("Codex CLI", "codex", None),
            ToolStatus("Claude Code", "claude", None),
        ]
        summary = run_local_install(
            config_path=config,
            template_path=template,
            codex_install_config=CodexInstallConfig(codex_home=codex_home),
        )

    text = format_install_summary(summary)

    assert "npm install -g @openai/codex --registry https://registry.npmmirror.com" in text
    assert (
        "npm install -g @anthropic-ai/claude-code --registry https://registry.npmmirror.com" in text
    )
