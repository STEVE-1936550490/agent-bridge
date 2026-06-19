"""OpenAI protocol handler for AgentBridge."""

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

from aiohttp import web

from ..config import Config
from ..observability import (
    REQ_CLIENT_PROTOCOL,
    REQ_MODEL,
    REQ_PROVIDER_PROTOCOL,
    REQ_STREAM_STATE,
    REQ_TOKEN_USAGE,
    TokenUsage,
)
from ..parsers.glm import ContentType, GLMParser
from ..transformers.anthropic import AnthropicTransformer
from ..transformers.codex import CodexResponseBuilder, CodexTransformer
from ..transformers.responses import ResponsesTransformer

if TYPE_CHECKING:
    import aiohttp

logger = logging.getLogger(__name__)


class OpenAIHandler:
    """
    Handle OpenAI-format requests and transform GLM responses.

    This handler:
    1. Receives OpenAI-format requests from clients
    2. Forwards to GLM upstream platform
    3. Parses GLM's non-standard streaming format
    4. Transforms to Codex-compatible response format
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.upstream_url = config.upstream.base_url.rstrip("/")
        self.api_key = config.upstream.api_key
        # Resolve the active provider's reasoning mode so per-request handlers
        # know how to translate Codex reasoning effort into upstream fields.
        try:
            self.reasoning_mode = config.get_provider().reasoning_mode
        except ValueError:
            self.reasoning_mode = "passthrough"

    def _prepare_upstream_request(
        self, client_request: web.Request, body: dict
    ) -> tuple[str, dict, dict]:
        """
        Prepare request for upstream GLM platform.

        Args:
            client_request: Original client request
            body: Request body from client

        Returns:
            Tuple of (url, headers, payload)
        """
        url = f"{self.upstream_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Ensure stream is enabled for proper parsing
        # GLM must stream to separate reasoning from content
        payload = {key: value for key, value in body.items() if value is not None}
        payload["stream"] = True
        # Ask OpenAI-compatible providers to emit token usage on the final
        # streaming chunk. Providers that ignore this field are unaffected.
        payload.setdefault("stream_options", {})["include_usage"] = True

        return url, headers, payload

    @staticmethod
    def _extract_reasoning_effort(body: dict) -> str | None:
        """Extract the reasoning effort the client requested, if any.

        Codex sends ``reasoning: {"effort": "..."}`` in Responses API requests.
        Chat Completions clients may send a top-level ``reasoning_effort``.
        """
        reasoning = body.get("reasoning")
        if isinstance(reasoning, dict):
            effort = reasoning.get("effort")
            if isinstance(effort, str):
                return effort
        effort = body.get("reasoning_effort")
        if isinstance(effort, str):
            return effort
        return None

    def _apply_reasoning_to_chat_body(self, chat_body: dict, effort: str | None) -> None:
        """Translate a client reasoning effort into upstream fields.

        - ``passthrough``: forward ``reasoning_effort`` as-is (OpenAI standard).
        - ``thinking``: map low efforts to ``thinking: disabled`` and high
          efforts to ``thinking: enabled`` (GLM / Zhipu convention).
        - ``none``: do not add any reasoning field.
        """
        if effort is None:
            return
        if self.reasoning_mode == "none":
            return
        if self.reasoning_mode == "thinking":
            # GLM only supports an on/off switch, not a graded effort.
            thinking_type = "disabled" if effort in {"minimal", "low"} else "enabled"
            chat_body["thinking"] = {"type": thinking_type}
            return
        # passthrough: forward the standard OpenAI field.
        chat_body["reasoning_effort"] = effort

    def _error_response(self, message: str, status: int) -> web.Response:
        """Return an OpenAI-shaped error response."""
        return web.json_response(
            {
                "error": {
                    "message": message,
                    "type": "agent_bridge_error",
                    "code": status,
                }
            },
            status=status,
        )

    async def _read_json_body(self, request: web.Request) -> dict | web.Response:
        """Read a JSON body and return a consistent error on invalid input."""
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return self._error_response("Invalid JSON body", 400)

        if not isinstance(body, dict):
            return self._error_response("JSON body must be an object", 400)

        return body

    async def _collect_chunks(
        self,
        chunks,
        include_reasoning: bool = False,
    ) -> tuple[str, str | None, TokenUsage]:
        """Collect parsed GLM chunks into content, finish reason and usage."""
        content_parts: list[str] = []
        finish_reason: str | None = None
        usage = TokenUsage()

        async for chunk in chunks:
            if chunk.content_type == ContentType.DONE:
                if chunk.usage:
                    usage = TokenUsage.from_usage_dict(chunk.usage)
                finish_reason = chunk.finish_reason or finish_reason or "stop"
                break

            if chunk.content_type == ContentType.REASONING and not include_reasoning:
                continue

            if chunk.content:
                content_parts.append(chunk.content)
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            if chunk.usage:
                usage = TokenUsage.from_usage_dict(chunk.usage)

        return "".join(content_parts), finish_reason or "stop", usage

    def _build_responses_json(
        self, model: str, content: str, usage: TokenUsage | None = None
    ) -> dict:
        """Build a non-streaming Responses API response."""
        transformer = ResponsesTransformer(model=model)
        completed_at = transformer.created_at
        usage_dict = {
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }
        return {
            "id": transformer.response_id,
            "object": "response",
            "created_at": transformer.created_at,
            "status": "completed",
            "background": False,
            "completed_at": completed_at,
            "error": None,
            "incomplete_details": None,
            "instructions": "",
            "model": model,
            "output": [
                {
                    "id": transformer.item_id,
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": content,
                            "annotations": [],
                            "logprobs": [],
                        }
                    ],
                }
            ],
            "usage": usage_dict,
        }

    def _build_completion_json(
        self,
        model: str,
        content: str,
        finish_reason: str = "stop",
        usage: TokenUsage | None = None,
    ) -> dict:
        """Build a non-streaming legacy completions response."""
        return {
            "id": f"cmpl-{uuid.uuid4().hex[:12]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "text": content,
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": usage.input_tokens if usage else 0,
                "completion_tokens": usage.output_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
        }

    def _format_completion_chunk(
        self,
        completion_id: str,
        model: str,
        created: int,
        text: str,
        finish_reason: str | None = None,
    ) -> str:
        """Format one legacy completions stream chunk."""
        chunk_data = {
            "id": completion_id,
            "object": "text_completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "text": text,
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": finish_reason,
                }
            ],
        }
        return f"data: {json.dumps(chunk_data)}\n\n"

    def _content_to_text(self, content) -> str:
        """Extract text from OpenAI/Codex content variants."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content") or item.get("output")
                    if isinstance(text, str):
                        text_parts.append(text)
            return " ".join(text_parts)

        return ""

    def _responses_tools_to_chat_tools(self, tools) -> list[dict] | None:
        """Convert Responses API function tools to Chat Completions tools."""
        if not isinstance(tools, list):
            return None

        converted_tools: list[dict] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                converted_tools.append(tool)
                continue

            if tool.get("type") != "function":
                continue

            name = tool.get("name")
            if not isinstance(name, str) or not name:
                continue

            converted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters") or {},
                    },
                }
            )

        return converted_tools or None

    def _responses_tool_choice_to_chat_tool_choice(self, tool_choice):
        """Convert Responses API tool_choice to Chat Completions shape."""
        if tool_choice in (None, "auto", "none", "required"):
            return tool_choice
        if not isinstance(tool_choice, dict):
            return None
        if tool_choice.get("type") != "function":
            return tool_choice
        name = tool_choice.get("name")
        if not isinstance(name, str) or not name:
            return None
        return {"type": "function", "function": {"name": name}}

    def _responses_input_to_messages(self, input_data) -> list[dict]:
        """Convert Responses API input into chat-completions messages."""
        if isinstance(input_data, str):
            return [{"role": "user", "content": input_data}]

        if not isinstance(input_data, list):
            return []

        converted_messages: list[dict] = []
        for item in input_data:
            if isinstance(item, str):
                converted_messages.append({"role": "user", "content": item})
                continue

            if not isinstance(item, dict):
                continue

            role = item.get("role", "user")
            item_type = item.get("type")

            if item_type == "function_call":
                name = item.get("name")
                arguments = item.get("arguments", "")
                call_id = item.get("call_id") or item.get("id")
                if isinstance(name, str) and isinstance(call_id, str):
                    converted_messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": (
                                            arguments
                                            if isinstance(arguments, str)
                                            else json.dumps(arguments)
                                        ),
                                    },
                                }
                            ],
                        }
                    )
                continue

            if item_type == "function_call_output":
                call_id = item.get("call_id")
                if isinstance(call_id, str):
                    converted_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": self._content_to_text(
                                item.get("output") or item.get("content")
                            ),
                        }
                    )
                continue

            content = item.get("content")
            if content is None and "text" in item:
                content = item.get("text")

            converted_messages.append(
                {
                    "role": role if isinstance(role, str) else "user",
                    "content": self._content_to_text(content),
                }
            )

        return converted_messages

    def _anthropic_content_to_text(self, content) -> str:
        """Extract text from Anthropic content blocks."""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "tool_result":
                    parts.append(self._content_to_text(item.get("content")))
        return " ".join(part for part in parts if part)

    def _anthropic_messages_to_chat_messages(self, body: dict) -> list[dict]:
        """Convert Anthropic Messages input to Chat Completions messages."""
        messages: list[dict] = []
        system = body.get("system")
        if system:
            messages.append({"role": "system", "content": self._anthropic_content_to_text(system)})

        for message in body.get("messages") or []:
            if not isinstance(message, dict):
                continue
            role = message.get("role", "user")
            content = message.get("content")
            if isinstance(content, list):
                tool_results = [
                    item
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "tool_result"
                ]
                tool_uses = [
                    item
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "tool_use"
                ]
                for tool_result in tool_results:
                    tool_use_id = tool_result.get("tool_use_id")
                    if isinstance(tool_use_id, str):
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_use_id,
                                "content": self._anthropic_content_to_text(
                                    tool_result.get("content")
                                ),
                            }
                        )
                if tool_uses and role == "assistant":
                    messages.append(
                        {
                            "role": "assistant",
                            "content": self._anthropic_content_to_text(content),
                            "tool_calls": [
                                {
                                    "id": item.get("id"),
                                    "type": "function",
                                    "function": {
                                        "name": item.get("name"),
                                        "arguments": json.dumps(item.get("input") or {}),
                                    },
                                }
                                for item in tool_uses
                                if item.get("id") and item.get("name")
                            ],
                        }
                    )
                    continue

            messages.append(
                {
                    "role": role if role in {"user", "assistant", "system"} else "user",
                    "content": self._anthropic_content_to_text(content),
                }
            )
        return messages

    def _anthropic_tools_to_chat_tools(self, tools) -> list[dict] | None:
        """Convert Anthropic tools to Chat Completions function tools."""
        if not isinstance(tools, list):
            return None
        converted: list[dict] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                continue
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema") or {},
                    },
                }
            )
        return converted or None

    async def handle_chat_completions(
        self, request: web.Request, session: "aiohttp.ClientSession | None"
    ) -> web.StreamResponse:
        """
        Handle /v1/chat/completions endpoint.

        Args:
            request: Client request
            session: HTTP session for upstream calls

        Returns:
            Streaming response in Codex format
        """
        if session is None:
            return self._error_response("Server not initialized", 500)

        body = await self._read_json_body(request)
        if isinstance(body, web.Response):
            return body

        # Override the client model with the provider-configured model so that
        # -p <platform> selections take effect regardless of the client profile.
        model = self.config.default_model
        body["model"] = model

        url, headers, payload = self._prepare_upstream_request(request, body)
        request[REQ_MODEL] = model
        request[REQ_CLIENT_PROTOCOL] = "openai_chat"
        request[REQ_PROVIDER_PROTOCOL] = "openai_chat"
        request[REQ_STREAM_STATE] = "streaming" if body.get("stream", False) else "buffering"
        client_wants_stream = bool(body.get("stream", False))

        logger.info("Forwarding chat request to %s", url)

        try:
            async with session.post(url, json=payload, headers=headers) as upstream_resp:
                if upstream_resp.status != 200:
                    error_body = await upstream_resp.text()
                    logger.error("Upstream error: %s - %s", upstream_resp.status, error_body)
                    return self._error_response(
                        f"Upstream error: {upstream_resp.status}: {error_body}",
                        upstream_resp.status,
                    )

                parser = GLMParser()
                parsed_chunks = parser.parse_stream(upstream_resp)

                if not client_wants_stream:
                    content, _finish_reason, usage = await self._collect_chunks(parsed_chunks)
                    request[REQ_TOKEN_USAGE] = usage
                    builder = CodexResponseBuilder(model=model)
                    return web.json_response(builder.build_response(content=content, usage=usage))

                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
                await response.prepare(request)

                transformer = CodexTransformer(model=model)
                async for sse_line in transformer.transform(parsed_chunks):
                    await response.write(sse_line.encode("utf-8"))
                request[REQ_TOKEN_USAGE] = transformer.usage

                await response.write_eof()
                return response

        except Exception as e:
            logger.exception("Error handling chat completions request")
            return self._error_response(f"Internal error: {str(e)}", 500)

    async def handle_completions(
        self, request: web.Request, session: "aiohttp.ClientSession | None"
    ) -> web.StreamResponse:
        """
        Handle /v1/completions endpoint (legacy format).

        Args:
            request: Client request
            session: HTTP session for upstream calls

        Returns:
            Streaming response in Codex format
        """
        if session is None:
            return self._error_response("Server not initialized", 500)

        body = await self._read_json_body(request)
        if isinstance(body, web.Response):
            return body

        # Convert legacy completions format to chat format
        prompt = body.get("prompt")
        if not prompt:
            return self._error_response("Missing prompt", 400)

        # Override the client model with the provider-configured model so that
        # -p <platform> selections take effect regardless of the client profile.
        # Wrap prompt in messages format for upstream
        chat_body = {
            "model": self.config.default_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": body.get("max_tokens"),
            "temperature": body.get("temperature"),
            "stream": body.get("stream", True),
        }
        self._apply_reasoning_to_chat_body(chat_body, self._extract_reasoning_effort(body))

        url, headers, payload = self._prepare_upstream_request(request, chat_body)
        model = chat_body.get("model", self.config.default_model)
        request[REQ_MODEL] = model
        request[REQ_CLIENT_PROTOCOL] = "openai_completion"
        request[REQ_PROVIDER_PROTOCOL] = "openai_chat"
        request[REQ_STREAM_STATE] = "streaming" if body.get("stream", False) else "buffering"
        client_wants_stream = bool(body.get("stream", False))

        logger.info("Forwarding completions request to %s", url)

        try:
            async with session.post(url, json=payload, headers=headers) as upstream_resp:
                if upstream_resp.status != 200:
                    error_body = await upstream_resp.text()
                    logger.error("Upstream error: %s - %s", upstream_resp.status, error_body)
                    return self._error_response(
                        f"Upstream error: {upstream_resp.status}: {error_body}",
                        upstream_resp.status,
                    )

                parser = GLMParser()
                parsed_chunks = parser.parse_stream(upstream_resp)

                if not client_wants_stream:
                    content, finish_reason, usage = await self._collect_chunks(parsed_chunks)
                    request[REQ_TOKEN_USAGE] = usage
                    return web.json_response(
                        self._build_completion_json(
                            model=model,
                            content=content,
                            finish_reason=finish_reason or "stop",
                            usage=usage,
                        )
                    )

                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
                await response.prepare(request)

                completion_id = f"cmpl-{uuid.uuid4().hex[:12]}"
                created = int(time.time())
                usage = TokenUsage()
                async for chunk in parsed_chunks:
                    if chunk.content_type == ContentType.DONE:
                        if chunk.usage:
                            usage = TokenUsage.from_usage_dict(chunk.usage)
                        break
                    if chunk.content_type == ContentType.REASONING:
                        continue
                    if chunk.usage:
                        usage = TokenUsage.from_usage_dict(chunk.usage)
                    if chunk.content or chunk.finish_reason:
                        sse_line = self._format_completion_chunk(
                            completion_id=completion_id,
                            model=model,
                            created=created,
                            text=chunk.content,
                            finish_reason=chunk.finish_reason,
                        )
                        await response.write(sse_line.encode("utf-8"))
                request[REQ_TOKEN_USAGE] = usage

                await response.write(b"data: [DONE]\n\n")

                await response.write_eof()
                return response

        except Exception as e:
            logger.exception("Error handling completions request")
            return self._error_response(f"Internal error: {str(e)}", 500)

    async def handle_responses(
        self, request: web.Request, session: "aiohttp.ClientSession | None"
    ) -> web.StreamResponse:
        """
        Handle /v1/responses endpoint (Responses API).

        Args:
            request: Client request
            session: HTTP session for upstream calls

        Returns:
            Streaming response
        """
        if session is None:
            return self._error_response("Server not initialized", 500)

        body = await self._read_json_body(request)
        if isinstance(body, web.Response):
            return body

        # Convert Responses API format to Chat Completions format
        # Responses API uses 'input' instead of 'messages'
        input_data = body.get("input", [])
        converted_messages = self._responses_input_to_messages(input_data)
        if not converted_messages:
            return self._error_response("Empty input", 400)

        # Override the client model with the provider-configured model so that
        # -p <platform> selections take effect regardless of the client profile.
        chat_body = {
            "model": self.config.default_model,
            "messages": converted_messages,  # Use converted messages
            "max_tokens": body.get("max_tokens"),
            "temperature": body.get("temperature"),
            "stream": True,  # Always stream for proper parsing
        }
        tools = self._responses_tools_to_chat_tools(body.get("tools"))
        if tools:
            chat_body["tools"] = tools
        tool_choice = self._responses_tool_choice_to_chat_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            chat_body["tool_choice"] = tool_choice
        self._apply_reasoning_to_chat_body(chat_body, self._extract_reasoning_effort(body))

        url, headers, payload = self._prepare_upstream_request(request, chat_body)
        model = chat_body.get("model", self.config.default_model)
        request[REQ_MODEL] = model
        request[REQ_CLIENT_PROTOCOL] = "codex_responses"
        request[REQ_PROVIDER_PROTOCOL] = "openai_chat"
        request[REQ_STREAM_STATE] = "streaming" if body.get("stream", False) else "buffering"
        client_wants_stream = bool(body.get("stream", False))

        logger.info("Forwarding responses request to %s", url)

        try:
            async with session.post(url, json=payload, headers=headers) as upstream_resp:
                if upstream_resp.status != 200:
                    error_body = await upstream_resp.text()
                    logger.error("Upstream error: %s - %s", upstream_resp.status, error_body)
                    return self._error_response(
                        f"Upstream error: {upstream_resp.status}: {error_body}",
                        upstream_resp.status,
                    )

                parser = GLMParser()
                parsed_chunks = parser.parse_stream(upstream_resp)

                if not client_wants_stream:
                    content, _finish_reason, usage = await self._collect_chunks(parsed_chunks)
                    request[REQ_TOKEN_USAGE] = usage
                    return web.json_response(
                        self._build_responses_json(model=model, content=content, usage=usage)
                    )

                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
                await response.prepare(request)

                transformer = ResponsesTransformer(model=model)
                async for sse_event in transformer.transform(parsed_chunks):
                    await response.write(sse_event.encode("utf-8"))
                request[REQ_TOKEN_USAGE] = transformer.usage

                await response.write_eof()
                return response

        except Exception as e:
            logger.exception("Error handling responses request")
            return self._error_response(f"Internal error: {str(e)}", 500)

    async def handle_anthropic_messages(
        self, request: web.Request, session: "aiohttp.ClientSession | None"
    ) -> web.StreamResponse:
        """Handle /v1/messages endpoint (Anthropic Messages API)."""
        if session is None:
            return self._error_response("Server not initialized", 500)

        body = await self._read_json_body(request)
        if isinstance(body, web.Response):
            return body

        messages = self._anthropic_messages_to_chat_messages(body)
        if not messages:
            return self._error_response("Empty messages", 400)

        # Override the client model with the provider-configured model so that
        # -p <platform> selections take effect regardless of the client profile.
        chat_body = {
            "model": self.config.default_model,
            "messages": messages,
            "max_tokens": body.get("max_tokens"),
            "temperature": body.get("temperature"),
            "stream": True,
        }
        tools = self._anthropic_tools_to_chat_tools(body.get("tools"))
        if tools:
            chat_body["tools"] = tools
        self._apply_reasoning_to_chat_body(chat_body, self._extract_reasoning_effort(body))

        url, headers, payload = self._prepare_upstream_request(request, chat_body)
        model = chat_body.get("model", self.config.default_model)
        request[REQ_MODEL] = model
        request[REQ_CLIENT_PROTOCOL] = "anthropic"
        request[REQ_PROVIDER_PROTOCOL] = "openai_chat"
        request[REQ_STREAM_STATE] = "streaming" if body.get("stream", False) else "buffering"
        client_wants_stream = bool(body.get("stream", False))

        logger.info("Forwarding anthropic messages request to %s", url)

        try:
            async with session.post(url, json=payload, headers=headers) as upstream_resp:
                if upstream_resp.status != 200:
                    error_body = await upstream_resp.text()
                    logger.error("Upstream error: %s - %s", upstream_resp.status, error_body)
                    return self._error_response(
                        f"Upstream error: {upstream_resp.status}: {error_body}",
                        upstream_resp.status,
                    )

                parser = GLMParser()
                parsed_chunks = parser.parse_stream(upstream_resp)
                transformer = AnthropicTransformer(model=model)

                if not client_wants_stream:
                    content, finish_reason, usage = await self._collect_chunks(parsed_chunks)
                    request[REQ_TOKEN_USAGE] = usage
                    stop_reason = (
                        "end_turn" if finish_reason == "stop" else finish_reason or "end_turn"
                    )
                    return web.json_response(
                        transformer.build_message_json(
                            content=content, stop_reason=stop_reason, usage=usage
                        )
                    )

                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
                await response.prepare(request)

                async for sse_event in transformer.transform_stream(parsed_chunks):
                    await response.write(sse_event.encode("utf-8"))
                request[REQ_TOKEN_USAGE] = transformer.usage

                await response.write_eof()
                return response

        except Exception as e:
            logger.exception("Error handling anthropic messages request")
            return self._error_response(f"Internal error: {str(e)}", 500)
