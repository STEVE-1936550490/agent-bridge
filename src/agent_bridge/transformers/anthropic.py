"""Anthropic protocol transformer."""

from __future__ import annotations

import json
import uuid
from typing import AsyncIterator

from ..observability import TokenUsage
from ..parsers.glm import ContentType, GLMStreamChunk


class AnthropicTransformer:
    """Transform parsed OpenAI/GLM chunks to Anthropic Messages events."""

    def __init__(self, model: str = "ZHIPU/GLM-5.1") -> None:
        self.model = model
        self.message_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.text_started = False
        self.text_index = 0
        self.tool_states: dict[int, dict] = {}
        self.usage = TokenUsage()

    def _event(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def format_message_start(self) -> str:
        data = {
            "type": "message_start",
            "message": {
                "id": self.message_id,
                "type": "message",
                "role": "assistant",
                "model": self.model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }
        return self._event("message_start", data)

    def format_text_start(self) -> str:
        self.text_started = True
        data = {
            "type": "content_block_start",
            "index": self.text_index,
            "content_block": {"type": "text", "text": ""},
        }
        return self._event("content_block_start", data)

    def format_text_delta(self, text: str) -> str:
        data = {
            "type": "content_block_delta",
            "index": self.text_index,
            "delta": {"type": "text_delta", "text": text},
        }
        return self._event("content_block_delta", data)

    def format_content_block_stop(self, index: int) -> str:
        return self._event("content_block_stop", {"type": "content_block_stop", "index": index})

    def _tool_output_index(self, upstream_index: int) -> int:
        return (1 if self.text_started else 0) + upstream_index

    def _tool_state(self, tool_call: dict) -> dict:
        upstream_index = int(tool_call.get("index", 0))
        state = self.tool_states.get(upstream_index)
        if state is None:
            state = {
                "index": self._tool_output_index(upstream_index),
                "id": tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": "",
                "input": "",
                "started": False,
                "stopped": False,
            }
            self.tool_states[upstream_index] = state

        if tool_call.get("id"):
            state["id"] = tool_call["id"]
        function = tool_call.get("function") or {}
        if function.get("name"):
            state["name"] = function["name"]
        return state

    def format_tool_start(self, state: dict) -> str:
        data = {
            "type": "content_block_start",
            "index": state["index"],
            "content_block": {
                "type": "tool_use",
                "id": state["id"],
                "name": state["name"],
                "input": {},
            },
        }
        return self._event("content_block_start", data)

    def format_tool_delta(self, state: dict, partial_json: str) -> str:
        state["input"] += partial_json
        data = {
            "type": "content_block_delta",
            "index": state["index"],
            "delta": {"type": "input_json_delta", "partial_json": partial_json},
        }
        return self._event("content_block_delta", data)

    def format_message_delta(self, stop_reason: str = "end_turn") -> str:
        data = {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": self.usage.output_tokens or 0},
        }
        return self._event("message_delta", data)

    def format_message_stop(self) -> str:
        return self._event("message_stop", {"type": "message_stop"})

    async def transform_stream(
        self,
        chunks: AsyncIterator[GLMStreamChunk],
        include_reasoning: bool = False,
    ) -> AsyncIterator[str]:
        """Transform GLM/OpenAI chunks to Anthropic SSE events."""
        yield self.format_message_start()

        async for chunk in chunks:
            if chunk.usage:
                self.usage = TokenUsage.from_usage_dict(chunk.usage)

            if chunk.content_type == ContentType.DONE:
                if self.text_started:
                    yield self.format_content_block_stop(self.text_index)
                for state in self.tool_states.values():
                    if not state["stopped"]:
                        yield self.format_content_block_stop(state["index"])
                        state["stopped"] = True
                stop_reason = "tool_use" if self.tool_states else "end_turn"
                yield self.format_message_delta(stop_reason=stop_reason)
                yield self.format_message_stop()
                break

            if chunk.content_type == ContentType.REASONING and not include_reasoning:
                continue

            if chunk.content_type == ContentType.TOOL_CALL:
                for tool_call in chunk.tool_calls or []:
                    state = self._tool_state(tool_call)
                    if not state["started"]:
                        yield self.format_tool_start(state)
                        state["started"] = True
                    function = tool_call.get("function") or {}
                    arguments = function.get("arguments")
                    if arguments:
                        yield self.format_tool_delta(state, arguments)
                continue

            if chunk.content:
                if not self.text_started:
                    yield self.format_text_start()
                yield self.format_text_delta(chunk.content)

    def build_message_json(
        self,
        content: str,
        stop_reason: str = "end_turn",
        usage: TokenUsage | None = None,
    ) -> dict:
        """Build a non-streaming Anthropic message response."""
        token_usage = usage if usage is not None else self.usage
        return {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "model": self.model,
            "content": [{"type": "text", "text": content}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": token_usage.input_tokens or 0,
                "output_tokens": token_usage.output_tokens or 0,
            },
        }
