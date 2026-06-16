"""CLI entry point for MOMA proxy."""

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
    run_codex_with_moma,
)
from .config import Config
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


def _run_server_from_args(args: argparse.Namespace) -> int:
    try:
        config = Config.from_file(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1

    # Override with CLI args
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port

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


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        description="MOMA Proxy - GLM-5.1 to Codex/Anthropic protocol conversion"
    )
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the local proxy server")
    _add_server_args(serve_parser)

    install_parser = subparsers.add_parser(
        "install-codex",
        help="Install or update the Codex MOMA provider/profile",
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
        help="Run Codex through the MOMA profile",
    )
    codex_parser.add_argument("--profile", default=DEFAULT_PROFILE)
    codex_parser.add_argument("--env-key", default=DEFAULT_ENV_KEY)
    codex_parser.add_argument("--api-key", default="dummy")
    codex_parser.add_argument("codex_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    argv = list(sys.argv[1:] if argv is None else argv)

    # Preserve the original CLI shape: `moma-proxy --config config.yaml`.
    if not argv or argv[0].startswith("-"):
        legacy_parser = argparse.ArgumentParser(
            description="MOMA Proxy - GLM-5.1 to Codex/Anthropic protocol conversion"
        )
        _add_server_args(legacy_parser)
        return _run_server_from_args(legacy_parser.parse_args(argv))

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _run_server_from_args(args)
    if args.command == "install-codex":
        return _install_codex_from_args(args)
    if args.command == "codex":
        return run_codex_with_moma(
            profile=args.profile,
            env_key=args.env_key,
            api_key=args.api_key,
            argv=args.codex_args,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
