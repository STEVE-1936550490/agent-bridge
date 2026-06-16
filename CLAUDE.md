# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an API proxy that bridges a mobile LLM platform (GLM-5.1) to Codex and Claude Code APIs. The platform only supports OpenAI protocol, but GLM-5.1 has a non-standard output format that includes reasoning context before the actual response, which standard proxies like ccswitch cannot handle.

## Key Architecture Decisions

### Problem Statement
- GLM-5.1 outputs reasoning context first, then the actual response
- Standard OpenAI-compatible proxies fail to parse this format correctly
- Need custom handling for the streaming response format

### Protocol Compatibility

**Phase 1 (Current): Codex Response Protocol**
- Accept OpenAI-format requests from clients
- Forward to GLM platform via OpenAI protocol
- Parse GLM's non-standard streaming format (reasoning + response)
- Return in Codex-compatible response format

**Phase 2 (TODO): Claude Code Anthropic Protocol**
- Accept Anthropic-format requests from Claude Code
- Convert Anthropic API format to OpenAI format for upstream
- Parse GLM responses and convert to Anthropic streaming format

### Response Format Handling

The proxy must handle GLM-5.1's unique output structure:
1. Reasoning context stream (non-standard format)
2. Actual content stream (standard OpenAI format)

The proxy needs to:
- Detect and separate reasoning from content
- Strip or transform reasoning if target protocol doesn't support it
- Maintain streaming behavior throughout

## Development Commands

```bash
# Use the conda env named after this repo when available
conda activate moma_proxy

# Install dependencies
pip install -e ".[dev]"

# Run the proxy
python -m moma_proxy --config config.yaml

# Run tests
pytest

# Run specific test
pytest tests/test_parser.py -v

# Run with coverage
pytest --cov=moma_proxy --cov-report=html

# Format code
black src tests
isort src tests

# Type check
mypy src
```

## Codex MOMA Profile

The operational goal is to let Codex use MOMA through this proxy without breaking the default Codex GPT setup.

- Keep `/root/.codex/config.toml` defaulting to OpenAI/GPT unless the user explicitly asks to switch the global default.
- Register the proxy as a custom provider in `/root/.codex/config.toml`:

```toml
[model_providers.mycodex]
name = "MOMA Proxy"
base_url = "http://127.0.0.1:8080/v1"
env_key = "MOMA_PROXY_API_KEY"
wire_api = "responses"
```

- Put the MOMA switch in `/root/.codex/moma.config.toml`:

```toml
model = "ZHIPU/GLM-5.1"
model_provider = "mycodex"
```

- `MOMA_PROXY_API_KEY` can be a dummy value because this proxy ignores the client-side key and uses `config.yaml` for the real MOMA upstream API key.
- Start the proxy before using the profile:

```bash
conda activate moma_proxy
python -m moma_proxy --config config.yaml --host 127.0.0.1 --port 8080
```

- Use MOMA from Codex explicitly:

```bash
codex -p moma
codex -p moma exec -C /root/moma_proxy "只输出 OK 两个字母，不要解释。"
```

- Default Codex remains `codex` and should still use OpenAI/GPT.
- Roll back global Codex config with the latest `/root/.codex/config.toml.bak-*` file, or set the first lines back to:

```toml
model = "gpt-5.5"
model_provider = "openai"
```

## Project Structure

```
moma_proxy/
├── src/moma_proxy/
│   ├── __init__.py
│   ├── main.py           # CLI entry point
│   ├── server.py         # Async HTTP server
│   ├── handlers/
│   │   ├── openai.py     # OpenAI protocol handlers
│   │   └── anthropic.py  # Anthropic protocol handlers (Phase 2)
│   ├── parsers/
│   │   └── glm.py        # GLM-5.1 response parser
│   ├── transformers/
│   │   ├── codex.py      # Transform to Codex format
│   │   └── anthropic.py  # Transform to Anthropic format (Phase 2)
│   └── config.py         # Configuration handling
├── tests/
├── config.yaml.example
└── pyproject.toml
```

## Configuration

The proxy requires configuration for:
- `upstream`: GLM platform endpoint URL and authentication
- `server`: Port binding and host
- `mode`: Target protocol (codex/anthropic)
- `logging`: Log level and format

## Important Notes

- This is a custom proxy because existing solutions (ccswitch) cannot handle GLM's reasoning context format
- Maintain backward compatibility with OpenAI protocol on the input side
- Streaming responses must be handled carefully to preserve the reasoning/content separation
- Use async/await throughout for non-blocking I/O
