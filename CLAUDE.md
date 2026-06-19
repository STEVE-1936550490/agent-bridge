# CLAUDE.md

This file gives Claude Code repository-specific guidance.

## Project

AgentBridge is a local agent gateway for Codex and Claude Code. The public CLI is
`agent-bridge`; the Python package is `agent_bridge`.

Legacy compatibility remains for migration only:

- `moma-proxy` CLI
- `moma` shortcut command
- `moma_proxy` Python import wrapper

Prefer new names in all new code, tests, and docs.

## Current Stable Paths

- Codex client protocol -> OpenAI Chat Completions provider protocol
- Claude Code Anthropic Messages client protocol -> OpenAI Chat Completions provider protocol

MOMA GLM-5.x is one OpenAI Chat Completions-compatible provider profile.

## Development Commands

```bash
pip install -e ".[dev]"
pytest tests -v
python -m agent_bridge --config config.yaml
agent-bridge
```

## Codex Profile

AgentBridge registers a Codex profile named `agent_bridge`. The legacy `moma`
command remains as a wrapper that launches this profile. The managed Codex
provider should be named `agent_bridge` and point to:

```text
http://127.0.0.1:17681/v1
```

The Codex-side env key is a dummy client-side key. The real upstream provider key
comes from `config.yaml`.

## Package Layout

```text
src/agent_bridge/      # main implementation
src/moma_proxy/        # compatibility import and python -m wrapper only
tests/
```

## Notes

- Keep protocol transforms isolated and testable.
- Do not commit `config.yaml`, `config_old.yaml`, local Codex settings, or API keys.
- Preserve Codex behavior when changing Claude Code or provider support.
