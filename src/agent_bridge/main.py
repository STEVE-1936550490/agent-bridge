"""CLI entry point for AgentBridge."""

import argparse
import logging
import sys
from pathlib import Path

from .codex import (
    DEFAULT_BASE_URL,
    DEFAULT_ENV_KEY,
    DEFAULT_MODEL,
    DEFAULT_PROFILE,
    DEFAULT_PROVIDER,
    CodexInstallConfig,
    default_codex_home,
    install_codex_profile,
    run_codex_with_agent_bridge,
)
from .config import Config
from .configure import (
    ConfigureOptions,
    ConfigureSummary,
    configure_provider,
    format_configure_summary,
)
from .installer import DEFAULT_NPM_REGISTRY, format_install_summary, run_local_install
from .launcher import RunConfig, run_managed_client
from .server import run_server


def _add_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--host",
        help="Override server host",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override server port",
    )


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--platform",
        "-p",
        help="Provider name from config providers",
    )
    parser.add_argument(
        "--base-url",
        help="Temporary provider base URL override",
    )
    parser.add_argument(
        "--api-key",
        help="Temporary provider API key override",
    )
    parser.add_argument(
        "--api-key-env",
        help="Environment variable containing the temporary provider API key",
    )
    parser.add_argument(
        "--model",
        help="Temporary default model override",
    )
    parser.add_argument(
        "--provider-api",
        choices=["openai_chat", "openai_responses", "anthropic_messages"],
        help="Provider API protocol",
    )
    parser.add_argument(
        "--client-protocol",
        choices=["codex_responses", "anthropic"],
        help="Client wire protocol",
    )


def _run_server_from_args(args: argparse.Namespace) -> int:
    try:
        config = Config.from_file(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Override with CLI args
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port
    try:
        config.apply_provider(
            getattr(args, "platform", None),
            base_url=getattr(args, "base_url", None),
            api_key=getattr(args, "api_key", None),
            api_key_env=getattr(args, "api_key_env", None),
            model=getattr(args, "model", None),
            provider_api=getattr(args, "provider_api", None),
            client_protocol=getattr(args, "client_protocol", None),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper()),
        format=config.logging.format,
    )

    run_server(config)
    return 0


def _install_codex_from_args(args: argparse.Namespace) -> int:
    install_config = CodexInstallConfig(
        codex_home=Path(args.codex_home).expanduser(),
        profile=args.profile,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        env_key=args.env_key,
    )
    config_path, profile_path = install_codex_profile(install_config)
    print(f"Updated Codex provider: {config_path}")
    print(f"Updated Codex profile: {profile_path}")
    print(f"Run MOMA Codex with: moma")
    print(f"Default Codex remains: codex")
    return 0


def _install_from_args(args: argparse.Namespace) -> int:
    install_config = CodexInstallConfig(
        codex_home=Path(args.codex_home).expanduser(),
        profile=args.profile,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        env_key=args.env_key,
    )
    try:
        summary = run_local_install(
            config_path=Path(args.config).expanduser(),
            template_path=Path(args.template).expanduser(),
            codex_install_config=install_config,
            install_codex_cli=args.install_codex_cli,
            install_claude_code=args.install_claude_code,
            install_codex_profile_enabled=not args.skip_codex_profile,
            npm_registry=args.npm_registry,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(format_install_summary(summary))
    return 0


def _run_from_args(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser()
    try:
        config = Config.from_file(config_path)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    host = args.host or config.server.host
    port = args.port or config.server.port
    run_config = RunConfig(
        config_path=config_path,
        host=host,
        port=port,
        client=args.client,
        platform=args.platform,
        base_url=args.base_url,
        api_key=args.api_key,
        api_key_env=args.api_key_env,
        model=args.model,
        provider_api=args.provider_api,
        client_protocol=args.client_protocol,
        codex_profile=args.codex_profile,
        codex_env_key=args.codex_env_key,
        codex_api_key=args.codex_api_key,
        claude_api_key=args.claude_api_key,
        client_args=args.client_args,
        startup_timeout=args.startup_timeout,
    )
    try:
        return run_managed_client(run_config)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _local_proxy_base_url(host: str, port: int) -> str:
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{connect_host}:{port}/v1"


def _sync_codex_profile_from_configure_args(
    args: argparse.Namespace,
    summary: ConfigureSummary,
) -> None:
    if args.skip_codex_profile or summary.client_protocol != "codex_responses":
        return
    install_codex_profile(
        CodexInstallConfig(
            codex_home=Path(args.codex_home).expanduser(),
            profile=args.codex_profile,
            provider=args.codex_provider,
            model=summary.model,
            base_url=_local_proxy_base_url(summary.host, summary.port),
            env_key=args.codex_env_key,
        )
    )


def _configure_from_args(args: argparse.Namespace) -> int:
    options = ConfigureOptions(
        config_path=Path(args.config).expanduser(),
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        api_key_env=args.api_key_env,
        model=args.model,
        provider_api=args.provider_api,
        client_protocol=args.client_protocol,
        host=args.host,
        port=args.port,
        interactive=not args.no_interactive,
    )
    try:
        summary = configure_provider(options)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _sync_codex_profile_from_configure_args(args, summary)
    print(format_configure_summary(summary))
    return 0


def _add_run_command(
    subparsers: argparse._SubParsersAction,
    name: str,
    *,
    help_text: str,
) -> argparse.ArgumentParser:
    run_parser = subparsers.add_parser(name, help=help_text)
    _add_server_args(run_parser)
    _add_provider_args(run_parser)
    run_parser.add_argument("--client", choices=["codex", "claude"], default="codex")
    run_parser.add_argument("--codex-profile", default=DEFAULT_PROFILE)
    run_parser.add_argument("--codex-env-key", default=DEFAULT_ENV_KEY)
    run_parser.add_argument("--codex-api-key", default="dummy")
    run_parser.add_argument("--claude-api-key", default="dummy")
    run_parser.add_argument("--startup-timeout", type=float, default=15.0)
    run_parser.add_argument("client_args", nargs=argparse.REMAINDER)
    return run_parser


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        description="AgentBridge - local gateway for Codex/Claude Code model providers"
    )
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the local proxy server")
    _add_server_args(serve_parser)
    _add_provider_args(serve_parser)

    _add_run_command(
        subparsers,
        "start",
        help_text="Start the default configured agent client",
    )
    _add_run_command(
        subparsers,
        "run",
        help_text="Start the proxy, wait for health, then run an agent client",
    )

    configure_parser = subparsers.add_parser(
        "configure",
        help="Interactively create or update provider config",
    )
    configure_parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    configure_parser.add_argument("--provider", default=None)
    configure_parser.add_argument("--base-url", default=None)
    configure_parser.add_argument("--api-key", default=None)
    configure_parser.add_argument("--api-key-env", default=None)
    configure_parser.add_argument("--model", default=None)
    configure_parser.add_argument(
        "--provider-api",
        choices=["openai_chat", "openai_responses", "anthropic_messages"],
        default=None,
    )
    configure_parser.add_argument(
        "--client-protocol",
        choices=["codex_responses", "anthropic"],
        default=None,
    )
    configure_parser.add_argument("--host", default=None)
    configure_parser.add_argument("--port", type=int, default=None)
    configure_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Write config from flags without prompting",
    )
    configure_parser.add_argument(
        "--skip-codex-profile",
        action="store_true",
        help="Do not update the Codex profile after writing config",
    )
    configure_parser.add_argument(
        "--codex-home",
        default=str(default_codex_home()),
        help="Codex home directory (default: $CODEX_HOME or ~/.codex)",
    )
    configure_parser.add_argument("--codex-profile", default=DEFAULT_PROFILE)
    configure_parser.add_argument("--codex-provider", default=DEFAULT_PROVIDER)
    configure_parser.add_argument("--codex-env-key", default=DEFAULT_ENV_KEY)

    setup_parser = subparsers.add_parser(
        "install",
        help="Run cross-platform local setup checks and create missing config/profile files",
    )
    setup_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config file to create if missing (default: config.yaml)",
    )
    setup_parser.add_argument(
        "--template",
        default="config.yaml.example",
        help="Config template path (default: config.yaml.example)",
    )
    setup_parser.add_argument(
        "--install-codex-cli",
        action="store_true",
        help="Install Codex CLI with npm if codex is not found",
    )
    setup_parser.add_argument(
        "--install-claude-code",
        action="store_true",
        help="Install Claude Code CLI with npm if claude is not found",
    )
    setup_parser.add_argument(
        "--npm-registry",
        default=DEFAULT_NPM_REGISTRY,
        help=f"npm registry for CLI installs (default: {DEFAULT_NPM_REGISTRY})",
    )
    setup_parser.add_argument(
        "--skip-codex-profile",
        action="store_true",
        help="Skip Codex provider/profile registration",
    )
    setup_parser.add_argument(
        "--codex-home",
        default=str(default_codex_home()),
        help="Codex home directory (default: $CODEX_HOME or ~/.codex)",
    )
    setup_parser.add_argument("--profile", default=DEFAULT_PROFILE)
    setup_parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    setup_parser.add_argument("--model", default=DEFAULT_MODEL)
    setup_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    setup_parser.add_argument("--env-key", default=DEFAULT_ENV_KEY)

    install_parser = subparsers.add_parser(
        "install-codex",
        help="Install or update the Codex AgentBridge provider/profile",
    )
    install_parser.add_argument(
        "--codex-home",
        default=str(default_codex_home()),
        help="Codex home directory (default: $CODEX_HOME or ~/.codex)",
    )
    install_parser.add_argument("--profile", default=DEFAULT_PROFILE)
    install_parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    install_parser.add_argument("--model", default=DEFAULT_MODEL)
    install_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    install_parser.add_argument("--env-key", default=DEFAULT_ENV_KEY)

    codex_parser = subparsers.add_parser(
        "codex",
        help="Run Codex through the AgentBridge profile",
    )
    codex_parser.add_argument("--profile", default=DEFAULT_PROFILE)
    codex_parser.add_argument("--env-key", default=DEFAULT_ENV_KEY)
    codex_parser.add_argument("--api-key", default="dummy")
    codex_parser.add_argument("codex_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    called_as = Path(sys.argv[0]).name
    argv = list(sys.argv[1:] if argv is None else argv)
    if called_as == "agent-bridge" and (not argv or argv[0].startswith("-")):
        if not argv or argv[0] not in {"-h", "--help"}:
            argv = ["start", *argv]

    # Preserve the direct server CLI shape for legacy entry points and python -m.
    if (not argv or argv[0].startswith("-")) and not (
        called_as == "agent-bridge" and argv and argv[0] in {"-h", "--help"}
    ):
        legacy_parser = argparse.ArgumentParser(
            description="AgentBridge - local gateway for Codex/Claude Code model providers"
        )
        _add_server_args(legacy_parser)
        _add_provider_args(legacy_parser)
        return _run_server_from_args(legacy_parser.parse_args(argv))

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _run_server_from_args(args)
    if args.command in {"start", "run"}:
        return _run_from_args(args)
    if args.command == "configure":
        return _configure_from_args(args)
    if args.command == "install":
        return _install_from_args(args)
    if args.command == "install-codex":
        return _install_codex_from_args(args)
    if args.command == "codex":
        return run_codex_with_agent_bridge(
            profile=args.profile,
            env_key=args.env_key,
            api_key=args.api_key,
            argv=args.codex_args,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
