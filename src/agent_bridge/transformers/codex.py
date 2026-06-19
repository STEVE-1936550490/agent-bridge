"""Transform GLM responses to Codex-compatible format."""

import json
import logging
import time
import uuid
from typing import AsyncIterator

from ..parsers.glm import ContentType, GLMStreamChunk

logger = logging.getLogger(__name__)


class CodexTransformer:
    """
    Transform GLM stream chunks to Codex-compatible response format.

    Codex expects standard OpenAI streaming format:
    data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk",
           "created":1234567890,"model":"gpt-4","choices":[{
           "index":0,"delta":{"content":"Hello"},"finish_reason":null}]}
    """

    def __init__(self, model: str = "glm-5.1"):
        self.model = model
        self.completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        self.created = int(time.time())
        self.role_sent = False

    def format_role_chunk(self) -> str:
        """Format the initial assistant role chunk."""
        chunk_data = {
            "id": self.completion_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                }
            ],
        }
        return f"data: {json.dumps(chunk_data)}\n\n"

    def format_chunk(self, content: str, finish_reason: str | None = None) -> str:
        """
        Format a single streaming chunk in OpenAI format.

        Args:
            content: Content for this chunk
            finish_reason: Optional finish reason

        Returns:
            Formatted SSE line
        """
        chunk_data = {
            "id": self.completion_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content} if content else {},
                    "finish_reason": finish_reason,
                }
            ],
        }
        return f"data: {json.dumps(chunk_data)}\n\n"

    def format_done(self) -> str:
        """Format the [DONE] marker."""
        return "data: [DONE]\n\n"

    async def transform(
        self, chunks: AsyncIterator[GLMStreamChunk], include_reasoning: bool = False
    ) -> AsyncIterator[str]:
        """
        Transform GLM chunks to Codex format.

        Args:
            chunks: Stream of parsed GLM chunks
            include_reasoning: Whether to include reasoning in output

        Yields:
            Formatted SSE lines for Codex compatibility
        """
        if not self.role_sent:
            self.role_sent = True
            yield self.format_role_chunk()

        async for chunk in chunks:
            if chunk.content_type == ContentType.DONE:
                # GLM's last content chunk already has finish_reason
                # Just output [DONE] marker
                yield self.format_done()
                break

            # Skip reasoning unless explicitly requested
            if chunk.content_type == ContentType.REASONING and not include_reasoning:
                continue

            # Transform content chunks
            if chunk.content:
                yield self.format_chunk(chunk.content, chunk.finish_reason)
            elif chunk.finish_reason:
                # Empty content with finish reason (GLM's final chunk)
                yield self.format_chunk("", chunk.finish_reason)


class CodexResponseBuilder:
    """Build non-streaming Codex responses."""

    def __init__(self, model: str = "glm-5.1"):
        self.model = model

    def build_response(
        self,
        content: str,
        reasoning: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> dict:
        """
        Build a non-streaming OpenAI-compatible response.

        Args:
            content: Main response content
            reasoning: Optional reasoning content (currently not included in Codex format)
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            OpenAI-format response dict
        """
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
