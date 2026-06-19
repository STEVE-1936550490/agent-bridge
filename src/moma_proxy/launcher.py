"""Process launcher for running the proxy and agent clients together."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .codex import DEFAULT_ENV_KEY, DEFAULT_PROFILE


@dataclass(frozen=True)
class RunConfig:
    """Configuration for one managed proxy/client run."""

    config_path: Path
    host: str
    port: int
    client: str = "codex"
    platform: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    provider_api: str | None = None
    client_protocol: str | None = None
    codex_profile: str = DEFAULT_PROFILE
    codex_env_key: str = DEFAULT_ENV_KEY
    codex_api_key: str = "dummy"
    claude_api_key: str = "dummy"
    client_args: list[str] | None = None
    startup_timeout: float = 15.0
    poll_interval: float = 0.2


def health_url(host: str, port: int) -> str:
    """Return the local proxy health URL."""
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{connect_host}:{port}/health"


def _append_optional_arg(command: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def build_proxy_command(config: RunConfig) -> list[str]:
    """Build the proxy subprocess command."""
    client_protocol = config.client_protocol
    if client_protocol is None and config.client == "claude":
        client_protocol = "anthropic"

    command = [
        sys.executable,
        "-m",
        "moma_proxy",
        "serve",
        "--config",
        str(config.config_path),
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    _append_optional_arg(command, "--platform", config.platform)
    _append_optional_arg(command, "--base-url", config.base_url)
    _append_optional_arg(command, "--api-key", config.api_key)
    _append_optional_arg(command, "--api-key-env", config.api_key_env)
    _append_optional_arg(command, "--model", config.model)
    _append_optional_arg(command, "--provider-api", config.provider_api)
    _append_optional_arg(command, "--client-protocol", client_protocol)
    return command


def build_client_command(config: RunConfig) -> list[str]:
    """Build the selected client command."""
    if config.client == "codex":
        executable = shutil.which("codex") or "codex"
        command = [executable, "-p", config.codex_profile]
        if config.client_args:
            command.extend(config.client_args)
        return command
    if config.client == "claude":
        executable = shutil.which("claude") or "claude"
        command = [executable]
        if config.client_args:
            command.extend(config.client_args)
        return command
    raise RuntimeError(f"Unsupported client: {config.client}")


def build_client_env(config: RunConfig) -> dict[str, str]:
    """Build environment variables for the selected client."""
    env = os.environ.copy()
    if config.client == "codex":
        env.setdefault(config.codex_env_key, config.codex_api_key)
    elif config.client == "claude":
        env["ANTHROPIC_BASE_URL"] = f"{health_url(config.host, config.port)[:-7]}/v1"
        if not env.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = config.claude_api_key
        if not env.get("ANTHROPIC_AUTH_TOKEN"):
            env["ANTHROPIC_AUTH_TOKEN"] = config.claude_api_key
    return env


def wait_for_health(url: str, timeout: float, poll_interval: float) -> bool:
    """Wait until the proxy health endpoint returns HTTP 200."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=poll_interval) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(poll_interval)
    return False


def terminate_process(process: subprocess.Popen) -> None:
    """Terminate a child process and force-kill it if needed."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _print_proxy_log_tail(log_file, line_count: int = 40) -> None:
    """Print recent proxy output after startup failure."""
    log_file.seek(0)
    lines = log_file.readlines()
    if not lines:
        return
    print("Proxy output:", file=sys.stderr)
    for line in lines[-line_count:]:
        print(line.rstrip(), file=sys.stderr)


def run_managed_client(config: RunConfig) -> int:
    """Start proxy, wait for health, run client, then clean up proxy."""
    proxy_command = build_proxy_command(config)
    print(f"Starting AgentBridge proxy: {' '.join(proxy_command)}", file=sys.stderr)
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as proxy_log:
        proxy = subprocess.Popen(
            proxy_command,
            stdout=proxy_log,
            stderr=subprocess.STDOUT,
        )
        try:
            url = health_url(config.host, config.port)
            if not wait_for_health(url, config.startup_timeout, config.poll_interval):
                returncode = proxy.poll()
                if returncode is not None:
                    print(
                        f"Error: proxy exited before becoming healthy: {returncode}",
                        file=sys.stderr,
                    )
                    _print_proxy_log_tail(proxy_log)
                    return returncode or 1
                print(f"Error: proxy did not become healthy at {url}", file=sys.stderr)
                _print_proxy_log_tail(proxy_log)
                return 1

            client_command = build_client_command(config)
            print(f"Starting {config.client}: {' '.join(client_command)}", file=sys.stderr)
            try:
                client = subprocess.Popen(client_command, env=build_client_env(config))
            except FileNotFoundError:
                print(f"Error: {config.client} command not found in PATH", file=sys.stderr)
                return 127
            return client.wait()
        finally:
            terminate_process(proxy)
