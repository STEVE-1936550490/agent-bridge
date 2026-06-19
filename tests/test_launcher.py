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
                        "api_key_env": "AGENT_BRIDGE_API_KEY",
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
                    "api_key": "${AGENT_BRIDGE_API_KEY}",
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


def test_sync_codex_profile_model_updates_profile_when_provider_changes(tmp_path: Path) -> None:
    """When -p selects a different provider, the Codex profile model is updated."""
    from agent_bridge.codex import CodexInstallConfig, profile_content, default_codex_home
    from agent_bridge.launcher import _sync_codex_profile_model, RunConfig

    # Create a config with two providers using different models
    config_data = {
        "active_provider": "moma_glm51",
        "providers": {
            "moma_glm51": {
                "base_url": "https://moma.example.com/v1",
                "api_key": "test-key",
                "model": "ZHIPU/GLM-5.1",
                "provider_api": "openai_chat",
                "client_protocol": "codex_responses",
            },
            "moma_glm52": {
                "base_url": "https://moma.example.com/v1",
                "api_key": "test-key",
                "model": "ZHIPU/GLM-5.2",
                "provider_api": "openai_chat",
                "client_protocol": "codex_responses",
            },
        },
        "server": {"host": "127.0.0.1", "port": 17681},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    # First, install a profile with the default model (GLM-5.1)
    codex_home = tmp_path / "codex_home"
    install_config = CodexInstallConfig(
        codex_home=codex_home,
        profile="agent_bridge",
        model="ZHIPU/GLM-5.1",
        base_url="http://127.0.0.1:17681/v1",
        env_key="AGENT_BRIDGE_API_KEY",
    )
    install_config.profile_path.parent.mkdir(parents=True, exist_ok=True)
    install_config.profile_path.write_text(profile_content(install_config), encoding="utf-8")

    # Verify initial model
    initial_content = install_config.profile_path.read_text(encoding="utf-8")
    assert 'model = "ZHIPU/GLM-5.1"' in initial_content

    # Now run sync with -p moma_glm52
    run_config = RunConfig(
        config_path=config_path,
        host="127.0.0.1",
        port=17681,
        client="codex",
        platform="moma_glm52",
        codex_profile="agent_bridge",
    )

    # Monkey-patch default_codex_home to use our temp dir
    import agent_bridge.launcher as launcher_mod

    original_codex_home = launcher_mod.default_codex_home
    launcher_mod.default_codex_home = lambda: codex_home
    try:
        _sync_codex_profile_model(run_config)
    finally:
        launcher_mod.default_codex_home = original_codex_home

    # Verify model was updated
    updated_content = install_config.profile_path.read_text(encoding="utf-8")
    assert 'model = "ZHIPU/GLM-5.2"' in updated_content
    assert 'model = "ZHIPU/GLM-5.1"' not in updated_content


def test_sync_codex_profile_model_skips_when_model_matches(tmp_path: Path) -> None:
    """When the provider model already matches the profile, no write occurs."""
    from agent_bridge.codex import CodexInstallConfig, profile_content
    from agent_bridge.launcher import _sync_codex_profile_model, RunConfig

    config_data = {
        "active_provider": "moma_glm51",
        "providers": {
            "moma_glm51": {
                "base_url": "https://moma.example.com/v1",
                "api_key": "test-key",
                "model": "ZHIPU/GLM-5.1",
                "provider_api": "openai_chat",
                "client_protocol": "codex_responses",
            },
        },
        "server": {"host": "127.0.0.1", "port": 17681},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    codex_home = tmp_path / "codex_home"
    install_config = CodexInstallConfig(
        codex_home=codex_home,
        profile="agent_bridge",
        model="ZHIPU/GLM-5.1",
        base_url="http://127.0.0.1:17681/v1",
        env_key="AGENT_BRIDGE_API_KEY",
    )
    install_config.profile_path.parent.mkdir(parents=True, exist_ok=True)
    install_config.profile_path.write_text(profile_content(install_config), encoding="utf-8")

    # Record mtime before sync
    import time

    mtime_before = install_config.profile_path.stat().st_mtime
    time.sleep(0.05)

    run_config = RunConfig(
        config_path=config_path,
        host="127.0.0.1",
        port=17681,
        client="codex",
        platform=None,  # Use default provider
        codex_profile="agent_bridge",
    )

    import agent_bridge.launcher as launcher_mod

    original_codex_home = launcher_mod.default_codex_home
    launcher_mod.default_codex_home = lambda: codex_home
    try:
        _sync_codex_profile_model(run_config)
    finally:
        launcher_mod.default_codex_home = original_codex_home

    # Profile should NOT have been rewritten (same mtime)
    mtime_after = install_config.profile_path.stat().st_mtime
    assert mtime_before == mtime_after


def test_sync_codex_profile_model_skips_non_codex_client(tmp_path: Path) -> None:
    """_sync_codex_profile_model does nothing for non-codex clients."""
    from agent_bridge.launcher import _sync_codex_profile_model, RunConfig

    config_data = {
        "active_provider": "moma_glm51",
        "providers": {
            "moma_glm51": {
                "base_url": "https://moma.example.com/v1",
                "api_key": "test-key",
                "model": "ZHIPU/GLM-5.1",
                "provider_api": "openai_chat",
                "client_protocol": "codex_responses",
            },
        },
        "server": {"host": "127.0.0.1", "port": 17681},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    # Claude client - should be a no-op
    run_config = RunConfig(
        config_path=config_path,
        host="127.0.0.1",
        port=17681,
        client="claude",
        platform="moma_glm51",
    )

    # Should not raise or write anything
    _sync_codex_profile_model(run_config)
