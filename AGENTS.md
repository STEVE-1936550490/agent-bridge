# AGENTS.md

This file gives coding agents the current product direction and engineering
constraints for this repository.

## Project Direction

AgentBridge is moving from a single MOMA-to-Codex compatibility proxy into a
cross-platform agent gateway. The target product should let users install,
configure, launch, observe, and debug agent clients through one consistent CLI
on Windows and Linux.

## Target Capabilities

1. Support Windows and Linux as first-class environments.
   - Avoid POSIX-only assumptions in paths, process management, shell snippets,
     installer scripts, and service startup.
   - Prefer Python standard library cross-platform APIs for filesystem,
     subprocess, networking, and signal handling.

2. Provide one-command installation.
   - Install this proxy package.
   - Detect and install or guide installation of Codex CLI and Claude Code when
     supported.
   - Install/register local launcher scripts.
   - Create or update default config files without overwriting user secrets.

3. Provide a CLI for provider and protocol selection.
   - Support `-p <platform>` to choose a provider at launch time.
   - Allow custom providers from the command line.
   - Track provider API protocol separately from client wire protocol.
   - Client protocols to support: Codex Responses stream first, Claude Code
     Anthropic stream later.
   - Provider protocols to support: OpenAI Chat Completions, Anthropic Messages,
     and OpenAI Responses.

4. Provide one-command runtime startup.
   - A command such as `agent-bridge run -p <platform> --client codex` should start the
     proxy, wait until it is healthy, then launch the selected agent client.
   - Users should not need two terminals for normal use.
   - Existing direct proxy startup should remain available for debugging and
     integration tests.

5. Add runtime observability.
   - Monitor proxy health, upstream errors, stream parser errors, client
     disconnects, request latency, retry behavior, and process lifecycle.
   - Emit structured logs that are useful for later optimization and bug
     reports.

6. Add a UI dashboard.
   - Show every request/log event in real time.
   - Include existing log fields plus request id, provider, model, endpoint,
     latency, status, streaming state, and error details.
   - Track input/output tokens when available from upstream usage payloads.
   - When usage is not provided, expose this clearly and optionally estimate
     token counts in a separate field so real and estimated values are not
     confused.

7. Rename after the above foundation is usable.
   - Use `AgentBridge` as the public product and CLI name now.
   - Keep the Python package name `moma_proxy` until the final naming/code review pass.

## Engineering Priorities

- Preserve current Codex behavior while expanding the architecture.
- Keep provider configuration data-driven; avoid hard-coding MOMA assumptions
  into generic protocol paths.
- Keep protocol transforms isolated and testable.
- Add tests before or with changes that affect streaming, tool calls, provider
  config, or process startup.
- Do not overwrite local user config files or secrets during installer work.

## Development Commands

```bash
pip install -e ".[dev]"
pytest tests -v
python -m moma_proxy --config config.yaml
```

## Current Compatibility Baseline

- Codex via OpenAI-compatible Responses API is the current primary target.
- MOMA GLM streaming reasoning/content separation is already part of the core
  parser responsibility.
- Anthropic/Claude Code support is planned but should not regress Codex.
