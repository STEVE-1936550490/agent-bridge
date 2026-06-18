"""Tests for managed proxy/client launcher."""

from pathlib import Path
from unittest.mock import patch

from moma_proxy.launcher import (
    RunConfig,
    build_client_command,
    build_client_env,
    build_proxy_command,
    health_url,
    run_managed_client,
)
from moma_proxy.main import main


def test_health_url_uses_loopback_for_wildcard_hosts() -> None:
    assert health_url("0.0.0.0", 17681) == "http://127.0.0.1:17681/health"
    assert health_url("127.0.0.1", 9000) == "http://127.0.0.1:9000/health"


def test_build_proxy_command_includes_provider_overrides(tmp_path: Path) -> None:
    config = RunConfig(
        config_path=tmp_path / "config.yaml",
        host="127.0.0.1",
        port=17681,
        platform="moma",
        model="custom-model",
        provider_api="openai_chat",
    )

    command = build_proxy_command(config)

    assert command[:4] == [command[0], "-m", "moma_proxy", "serve"]
    assert "--platform" in command
    assert "moma" in command
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

    assert build_client_command(config) == ["codex", "-p", "moma", "exec", "hello"]


def test_build_client_command_and_env_for_claude() -> None:
    config = RunConfig(
        config_path=Path("config.yaml"),
        host="0.0.0.0",
        port=17681,
        client="claude",
        client_args=["--help"],
    )

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

    def fake_popen(command, env=None):
        process = FakeProcess(command, env=env)
        created.append(process)
        return process

    config = RunConfig(
        config_path=tmp_path / "config.yaml",
        host="127.0.0.1",
        port=17681,
        client_args=["exec", "hello"],
    )

    with patch("moma_proxy.launcher.wait_for_health", return_value=True):
        with patch("moma_proxy.launcher.subprocess.Popen", fake_popen):
            result = run_managed_client(config)

    assert result == 0
    assert created[0].command[2:4] == ["moma_proxy", "serve"]
    assert created[1].command == ["codex", "-p", "moma", "exec", "hello"]
    assert created[1].env["MOMA_PROXY_API_KEY"] == "dummy"
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

    with patch("moma_proxy.launcher.wait_for_health", return_value=False):
        with patch("moma_proxy.launcher.subprocess.Popen", return_value=FakeProcess()):
            result = run_managed_client(
                RunConfig(
                    config_path=tmp_path / "config.yaml",
                    host="127.0.0.1",
                    port=17681,
                )
            )

    assert result == 1
    assert terminated is True
