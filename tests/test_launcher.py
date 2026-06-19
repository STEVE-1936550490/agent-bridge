"""Tests for managed proxy/client launcher."""

from pathlib import Path
from unittest.mock import patch

import yaml

from agent_bridge.launcher import (
    RunConfig,
    build_client_command,
    build_client_env,
    build_proxy_command,
    health_url,
    run_managed_client,
)
from agent_bridge.main import main


def test_health_url_uses_loopback_for_wildcard_hosts() -> None:
    assert health_url("0.0.0.0", 17681) == "http://127.0.0.1:17681/health"
    assert health_url("127.0.0.1", 9000) == "http://127.0.0.1:9000/health"


def test_build_proxy_command_includes_provider_overrides(tmp_path: Path) -> None:
    config = RunConfig(
        config_path=tmp_path / "config.yaml",
        host="127.0.0.1",
        port=17681,
        platform="moma_glm51",
        model="custom-model",
        provider_api="openai_chat",
    )

    command = build_proxy_command(config)

    assert command[:4] == [command[0], "-m", "agent_bridge", "serve"]
    assert "--platform" in command
    assert "moma_glm51" in command
    assert "--model" in command
    assert "custom-model" in command
    assert "--provider-api" in command


def test_build_client_command_for_codex() -> None:
    config = RunConfig(
        config_path=Path("config.yaml"),
        host="127.0.0.1",
        port=17681,
        client_args=["exec", "hello"],
    )

    with patch("agent_bridge.launcher.shutil.which", return_value=None):
        command = build_client_command(config)

    assert command == ["codex", "-p", "agent_bridge", "exec", "hello"]


def test_build_client_command_resolves_windows_command_shim() -> None:
    config = RunConfig(
        config_path=Path("config.yaml"),
        host="127.0.0.1",
        port=17681,
    )

    with patch("agent_bridge.launcher.shutil.which", return_value=r"C:\npm\codex.cmd"):
        command = build_client_command(config)

    assert command == [r"C:\npm\codex.cmd", "-p", "agent_bridge"]


def test_build_client_command_and_env_for_claude() -> None:
    config = RunConfig(
        config_path=Path("config.yaml"),
        host="0.0.0.0",
        port=17681,
        client="claude",
        client_args=["--help"],
    )

    with patch("agent_bridge.launcher.shutil.which", return_value=None):
        command = build_client_command(config)
    env = build_client_env(config)

    assert command == ["claude", "--help"]
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:17681/v1"
    assert env["ANTHROPIC_API_KEY"] == "dummy"


def test_build_proxy_command_defaults_claude_to_anthropic_protocol() -> None:
    config = RunConfig(
        config_path=Path("config.yaml"),
        host="127.0.0.1",
        port=17681,
        client="claude",
    )

    command = build_proxy_command(config)

    assert "--client-protocol" in command
    assert "anthropic" in command


def test_run_managed_client_starts_proxy_then_client_and_cleans_up(tmp_path: Path) -> None:
    events: list[str] = []

    class FakeProcess:
        def __init__(self, command, env=None):
            self.command = command
            self.env = env
            self.returncode = None
            events.append(command[0])

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def terminate(self):
            events.append("terminate")
            self.returncode = 0

        def kill(self):
            events.append("kill")
            self.returncode = 1

    created: list[FakeProcess] = []

    def fake_popen(command, env=None, stdout=None, stderr=None):
        process = FakeProcess(command, env=env)
        created.append(process)
        return process

    config = RunConfig(
        config_path=tmp_path / "config.yaml",
        host="127.0.0.1",
        port=17681,
        client_args=["exec", "hello"],
    )

    with patch("agent_bridge.launcher.shutil.which", return_value=None):
        with patch("agent_bridge.launcher.wait_for_health", return_value=True):
            with patch("agent_bridge.launcher.subprocess.Popen", fake_popen):
                result = run_managed_client(config)

    assert result == 0
    assert created[0].command[2:4] == ["agent_bridge", "serve"]
    assert created[1].command == ["codex", "-p", "agent_bridge", "exec", "hello"]
    assert created[1].env["AGENT_BRIDGE_API_KEY"] == "dummy"
    assert "terminate" in events


def test_run_managed_client_cleans_proxy_when_health_fails(tmp_path: Path) -> None:
    terminated = False

    class FakeProcess:
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def terminate(self):
            nonlocal terminated
            terminated = True
            self.returncode = 0

        def kill(self):
            self.returncode = 1

    with patch("agent_bridge.launcher.wait_for_health", return_value=False):
        with patch("agent_bridge.launcher.subprocess.Popen", return_value=FakeProcess()):
            result = run_managed_client(
                RunConfig(
                    config_path=tmp_path / "config.yaml",
                    host="127.0.0.1",
                    port=17681,
                )
            )

    assert result == 1
    assert terminated is True


def test_main_start_uses_run_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "active_provider": "moma_glm51",
                "providers": {
                    "moma_glm51": {
                        "base_url": "https://moma.example.com/v1",
                        "api_key_env": "MOMA_API_KEY",
                        "model": "ZHIPU/GLM-5.1",
                        "provider_api": "openai_chat",
                        "client_protocol": "codex_responses",
                    }
                },
                "server": {"host": "127.0.0.1", "port": 19002},
            }
        ),
        encoding="utf-8",
    )

    captured: list[RunConfig] = []

    def fake_run(config: RunConfig) -> int:
        captured.append(config)
        return 0

    with patch("agent_bridge.main.run_managed_client", fake_run):
        result = main(["start", "--config", str(config_path), "exec", "hello"])

    assert result == 0
    assert captured[0].config_path == config_path
    assert captured[0].host == "127.0.0.1"
    assert captured[0].port == 19002
    assert captured[0].client == "codex"
    assert captured[0].client_args == ["exec", "hello"]


def test_agent_bridge_options_without_subcommand_default_to_start(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "upstream": {
                    "base_url": "https://moma.example.com/v1",
                    "api_key": "${MOMA_API_KEY}",
                },
                "server": {"host": "127.0.0.1", "port": 19003},
            }
        ),
        encoding="utf-8",
    )

    captured: list[RunConfig] = []

    def fake_run(config: RunConfig) -> int:
        captured.append(config)
        return 0

    with patch("agent_bridge.main.run_managed_client", fake_run):
        with patch("sys.argv", ["agent-bridge", "--config", str(config_path)]):
            result = main()

    assert result == 0
    assert captured[0].config_path == config_path
    assert captured[0].client == "codex"
