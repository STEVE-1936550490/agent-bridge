"""Backward-compatible import aliases for the old moma_proxy package name."""

from __future__ import annotations

import importlib
import sys

from agent_bridge import __version__

_ALIASES = [
    "codex",
    "codex_cli",
    "config",
    "configure",
    "dashboard",
    "handlers",
    "handlers.openai",
    "installer",
    "launcher",
    "main",
    "observability",
    "parsers",
    "parsers.glm",
    "server",
    "transformers",
    "transformers.anthropic",
    "transformers.codex",
    "transformers.responses",
]

for _name in _ALIASES:
    sys.modules[f"moma_proxy.{_name}"] = importlib.import_module(f"agent_bridge.{_name}")

__all__ = ["__version__"]
