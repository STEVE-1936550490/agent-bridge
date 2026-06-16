# MOMA Proxy Roadmap

## Ultimate goal

Make this project the single installable bridge for using MOMA platform APIs with
agent clients:

- Codex first: after installation, `moma` should start Codex through the MOMA API
  with normal agent behavior, including tool calls and follow-up turns.
- Provider-contained: the project should own proxy startup, Codex profile setup,
  and required environment variables instead of depending on external switchers.
- Extensible later: keep protocol boundaries clean enough to add clients such as
  Claude Code after Codex is stable.

## Current Codex compatibility target

Codex talks to custom providers through the OpenAI-compatible Responses API. The
proxy translates that to the MOMA platform's Chat Completions API:

```text
Codex /v1/responses
  -> moma_proxy
  -> MOMA /v1/chat/completions
```

For full agent behavior, the proxy must bridge both text and tool calls:

- Convert Responses API function tools to Chat Completions `tools`.
- Convert Responses API function call outputs back to Chat Completions `tool`
  messages.
- Parse upstream streaming `delta.tool_calls`.
- Emit Responses API function call SSE events so Codex can execute tools and
  send results in the next request.

## Implemented

- Basic Codex `moma` wrapper: `/root/.local/bin/moma`.
- Responses API text streaming.
- Standard Chat Completions `delta.tool_calls` parsing.
- Responses API function tool request conversion.
- Responses API function call SSE event emission.

## Next validation step ️ COMPLETED

Run a real `moma` Codex session against MOMA and inspect whether the upstream
GLM model returns standard `delta.tool_calls`. **Result: MOMA uses standard
OpenAI tool_calls format** - no extra parser branch needed.

Validation evidence in memory: `moma-tool-call-format-validation.md`.
