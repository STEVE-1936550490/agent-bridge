"""Structured request logging primitives."""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from aiohttp import web

TokenUsageSource = Literal["upstream", "estimated", "unavailable"]


def _aiohttp_key(
    kind: str,
    name: str,
    value_type: type,
) -> Any:
    """Return typed aiohttp keys when available, otherwise plain string keys."""
    key_factory = getattr(web, kind, None)
    if key_factory is None:
        return name
    return key_factory(name, value_type)


APP_CONFIG = _aiohttp_key("AppKey", "config", object)
APP_REQUEST_LOGS = _aiohttp_key("AppKey", "request_logs", object)
REQ_CLIENT_PROTOCOL = _aiohttp_key("RequestKey", "client_protocol", str)
REQ_MODEL = _aiohttp_key("RequestKey", "model", str)
REQ_PROVIDER_PROTOCOL = _aiohttp_key("RequestKey", "provider_protocol", str)
REQ_REQUEST_ID = _aiohttp_key("RequestKey", "request_id", str)
REQ_STREAM_STATE = _aiohttp_key("RequestKey", "stream_state", str)
REQ_TOKEN_USAGE = _aiohttp_key("RequestKey", "token_usage", object)


@dataclass(frozen=True)
class TokenUsage:
    """Token usage attached to a request log."""

    source: TokenUsageSource = "unavailable"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class RequestLog:
    """One structured request log event."""

    request_id: str
    timestamp: float
    method: str
    path: str
    status: int
    latency_ms: float
    provider: str | None
    model: str
    endpoint: str
    client_protocol: str | None
    provider_protocol: str | None
    stream_state: str
    error: str | None = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["timestamp_iso"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(self.timestamp),
        )
        return data


class RequestLogStore:
    """In-memory bounded request log store."""

    def __init__(self, max_entries: int = 500) -> None:
        self._entries: deque[RequestLog] = deque(maxlen=max_entries)

    def append(self, log: RequestLog) -> None:
        self._entries.append(log)

    def list(self, limit: int | None = None) -> list[dict]:
        entries = list(self._entries)
        if limit is not None:
            entries = entries[-limit:]
        return [entry.to_dict() for entry in entries]


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"
