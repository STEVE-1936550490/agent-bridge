"""Transform Chat Completions responses to Responses API format (WebSocket)."""

import json
import time
import uuid
from typing import AsyncIterator

from ..parsers.glm import ContentType, GLMStreamChunk


class ResponsesTransformer:
    """
    Transform GLM Chat Completions chunks to OpenAI Responses API WebSocket format.

    Based on real Codex logs, correct format is:
    - response.created: Initial response creation
    - response.output_text.delta: Text streaming (with item_id, sequence_number)
    - response.completed: Response finished (NOT response.done)
    """

    def __init__(self, model: str = "ZHIPU/GLM-5.1"):
        self.model = model
        self.response_id = f"resp_{uuid.uuid4().hex[:24]}"
        self.item_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.created_at = int(time.time())
        self.sequence_number = 0
        self.text_sent = False
        self.full_text = ""
        self.tool_calls: dict[int, dict] = {}
        self.output_items: list[dict] = []

    def format_response_created(self) -> str:
        """Format the response.created event."""
        event_data = {
            "type": "response.created",
            "response": {
                "id": self.response_id,
                "object": "response",
                "created_at": self.created_at,
                "status": "in_progress",
                "background": False,
                "completed_at": None,
                "error": None,
                "frequency_penalty": 0.0,
                "incomplete_details": None,
                "instructions": "",
            },
        }
        return f"event: response.created\ndata: {json.dumps(event_data)}\n\n"

    def format_response_in_progress(self) -> str:
        """Format the response.in_progress event."""
        event_data = {
            "type": "response.in_progress",
            "response": {
                "id": self.response_id,
                "object": "response",
                "created_at": self.created_at,
                "status": "in_progress",
                "model": self.model,
                "output": [],
            },
        }
        return f"event: response.in_progress\ndata: {json.dumps(event_data)}\n\n"

    def format_output_item_added(self) -> str:
        """Format the message item creation event."""
        event_data = {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": self.item_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        }
        return f"event: response.output_item.added\ndata: {json.dumps(event_data)}\n\n"

    def format_content_part_added(self) -> str:
        """Format the text content part creation event."""
        event_data = {
            "type": "response.content_part.added",
            "item_id": self.item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {
                "type": "output_text",
                "text": "",
                "annotations": [],
                "logprobs": [],
            },
        }
        return f"event: response.content_part.added\ndata: {json.dumps(event_data)}\n\n"

    def format_output_text_delta(self, content: str) -> str:
        """Format a text delta event."""
        self.text_sent = True
        self.full_text += content
        self.sequence_number += 1

        event_data = {
            "type": "response.output_text.delta",
            "content_index": 0,
            "delta": content,
            "item_id": self.item_id,  # Use item_id, not response_id
            "logprobs": [],
            "obfuscation": "",
            "output_index": 0,
            "sequence_number": self.sequence_number,
        }
        return f"event: response.output_text.delta\ndata: {json.dumps(event_data)}\n\n"

    def format_output_text_done(self) -> str:
        """Format the final text content event."""
        event_data = {
            "type": "response.output_text.done",
            "content_index": 0,
            "item_id": self.item_id,
            "logprobs": [],
            "output_index": 0,
            "sequence_number": self.sequence_number + 1,
            "text": self.full_text,
        }
        return f"event: response.output_text.done\ndata: {json.dumps(event_data)}\n\n"

    def format_content_part_done(self) -> str:
        """Format the text content part completion event."""
        event_data = {
            "type": "response.content_part.done",
            "item_id": self.item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {
                "type": "output_text",
                "text": self.full_text,
                "annotations": [],
                "logprobs": [],
            },
        }
        return f"event: response.content_part.done\ndata: {json.dumps(event_data)}\n\n"

    def format_output_item_done(self) -> str:
        """Format the message item completion event."""
        item = {
            "id": self.item_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": self.full_text,
                    "annotations": [],
                    "logprobs": [],
                }
            ],
        }
        self.output_items.append(item)
        event_data = {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": item,
        }
        return f"event: response.output_item.done\ndata: {json.dumps(event_data)}\n\n"

    def _tool_output_index(self, tool_index: int) -> int:
        return (1 if self.text_sent else 0) + tool_index

    def _get_tool_call_state(self, tool_call: dict) -> dict:
        index = int(tool_call.get("index", 0))
        state = self.tool_calls.get(index)
        if state is None:
            call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:24]}"
            state = {
                "id": f"fc_{uuid.uuid4().hex[:24]}",
                "call_id": call_id,
                "name": "",
                "arguments": "",
                "added": False,
                "done": False,
                "output_index": self._tool_output_index(index),
            }
            self.tool_calls[index] = state

        if tool_call.get("id"):
            state["call_id"] = tool_call["id"]
        function = tool_call.get("function") or {}
        if function.get("name"):
            state["name"] = function["name"]
        return state

    def format_function_call_added(self, state: dict) -> str:
        """Format a function call item creation event."""
        event_data = {
            "type": "response.output_item.added",
            "output_index": state["output_index"],
            "item": {
                "id": state["id"],
                "type": "function_call",
                "status": "in_progress",
                "call_id": state["call_id"],
                "name": state["name"],
                "arguments": "",
            },
        }
        return f"event: response.output_item.added\ndata: {json.dumps(event_data)}\n\n"

    def format_function_call_arguments_delta(self, state: dict, delta: str) -> str:
        """Format a function call arguments delta event."""
        state["arguments"] += delta
        event_data = {
            "type": "response.function_call_arguments.delta",
            "item_id": state["id"],
            "output_index": state["output_index"],
            "delta": delta,
        }
        return f"event: response.function_call_arguments.delta\ndata: {json.dumps(event_data)}\n\n"

    def format_function_call_arguments_done(self, state: dict) -> str:
        """Format a function call arguments completion event."""
        event_data = {
            "type": "response.function_call_arguments.done",
            "item_id": state["id"],
            "output_index": state["output_index"],
            "arguments": state["arguments"],
        }
        return f"event: response.function_call_arguments.done\ndata: {json.dumps(event_data)}\n\n"

    def format_function_call_done(self, state: dict) -> str:
        """Format a function call item completion event."""
        item = {
            "id": state["id"],
            "type": "function_call",
            "status": "completed",
            "call_id": state["call_id"],
            "name": state["name"],
            "arguments": state["arguments"],
        }
        self.output_items.append(item)
        event_data = {
            "type": "response.output_item.done",
            "output_index": state["output_index"],
            "item": item,
        }
        return f"event: response.output_item.done\ndata: {json.dumps(event_data)}\n\n"

    def finish_open_tool_calls(self) -> list[str]:
        """Finish any function call items accumulated from streaming deltas."""
        events: list[str] = []
        for index in sorted(self.tool_calls):
            state = self.tool_calls[index]
            if state["done"]:
                continue
            events.append(self.format_function_call_arguments_done(state))
            events.append(self.format_function_call_done(state))
            state["done"] = True
        return events

    def format_response_completed(self) -> str:
        """Format the response completion event."""
        completed_at = int(time.time())
        event_data = {
            "type": "response.completed",  # NOT response.done
            "response": {
                "id": self.response_id,
                "object": "response",
                "created_at": self.created_at,
                "status": "completed",
                "background": False,
                "completed_at": completed_at,
                "error": None,
                "frequency_penalty": 0.0,
                "incomplete_details": None,
                "instructions": "",
                "model": self.model,
                "output": self.output_items,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        }
        return f"event: response.completed\ndata: {json.dumps(event_data)}\n\n"

    async def transform(
        self, chunks: AsyncIterator[GLMStreamChunk], include_reasoning: bool = False
    ) -> AsyncIterator[str]:
        """
        Transform GLM Chat Completions chunks to Responses API format.

        Args:
            chunks: Stream of parsed GLM chunks
            include_reasoning: Whether to include reasoning in output

        Yields:
            Formatted SSE events for Responses API
        """
        # Send response.created first
        yield self.format_response_created()
        yield self.format_response_in_progress()

        async for chunk in chunks:
            if chunk.content_type == ContentType.DONE:
                # Finish the response with response.completed
                if self.text_sent:
                    yield self.format_output_text_done()
                    yield self.format_content_part_done()
                    yield self.format_output_item_done()
                for event in self.finish_open_tool_calls():
                    yield event
                yield self.format_response_completed()
                break

            # Skip reasoning unless explicitly requested
            if chunk.content_type == ContentType.REASONING and not include_reasoning:
                continue

            if chunk.content_type == ContentType.TOOL_CALL:
                for tool_call in chunk.tool_calls or []:
                    state = self._get_tool_call_state(tool_call)
                    if not state["added"]:
                        yield self.format_function_call_added(state)
                        state["added"] = True

                    function = tool_call.get("function") or {}
                    arguments_delta = function.get("arguments")
                    if arguments_delta:
                        yield self.format_function_call_arguments_delta(state, arguments_delta)
                continue

            # Send text deltas
            if chunk.content:
                if not self.text_sent:
                    yield self.format_output_item_added()
                    yield self.format_content_part_added()
                yield self.format_output_text_delta(chunk.content)
