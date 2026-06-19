"""Legacy console entry point for running Codex through AgentBridge."""

from __future__ import annotations

import sys

from .codex import DEFAULT_ENV_KEY, DEFAULT_PROFILE, run_codex_with_agent_bridge


def main() -> int:
    """Run Codex with the AgentBridge profile and required client-side key."""
    return run_codex_with_agent_bridge(
        profile=DEFAULT_PROFILE,
        env_key=DEFAULT_ENV_KEY,
        argv=sys.argv[1:],
    )


if __name__ == "__main__":
    sys.exit(main())
