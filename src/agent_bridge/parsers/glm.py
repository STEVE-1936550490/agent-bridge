"""GLM-5.1 response parser for non-standard streaming format."""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Type of content in GLM stream."""

    REASONING = "reasoning"
    CONTENT = "content"
    TOOL_CALL = "tool_call"
    DONE = "done"


@dataclass
class GLMStreamChunk:
    """Parsed chunk from GLM streaming response."""

    content_type: ContentType
    content: str
    raw_chunk: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None
    usage: dict | None = None


class GLMParser:
    """
    Parser for GLM-5.1's non-standard streaming format.

    GLM-5.1 outputs reasoning context before actual content.
    The format appears to be:
    - Initial chunks with reasoning context (marked or unmarked)
    - Followed by actual response content
    - Standard OpenAI format chunks

    This parser detects and separates these components.

    Token usage handling:
    When the upstream is asked for usage via ``stream_options.include_usage``
    (an OpenAI-standard field), the provider sends a final streaming chunk
    whose ``choices`` is empty and whose top-level ``usage`` carries the token
    counts. Some providers instead attach ``usage`` to the last content chunk.
    Both shapes are supported here: the usage dict is forwarded on the parsed
    chunk regardless of where it appears, and an empty-choices usage chunk is
    emitted as an empty content chunk so the stream is not terminated early.
    """

    def __init__(self) -> None:
        self.in_reasoning = True
        self.buffer = ""

    def parse_sse_line(self, line: str) -> GLMStreamChunk | None:
        """
        Parse a single SSE line from GLM response.

        Args:
            line: Raw SSE line (e.g., "data: {...}")

        Returns:
            Parsed chunk or None if line should be skipped
        """
        if not line or line.startswith(":"):
            # Skip empty lines and comments
            return None

        if line == "data: [DONE]":
            return GLMStreamChunk(
                content_type=ContentType.DONE,
                content="",
                raw_chunk=line,
                finish_reason="stop",
            )

        if not line.startswith("data: "):
            return None

        # Extract JSON payload
        json_str = line[6:]  # Remove "data: " prefix

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {json_str}")
            return None

        return self._parse_openai_chunk(data, line)

    def _parse_openai_chunk(self, data: dict, raw_line: str) -> GLMStreamChunk | None:
        """
        Parse OpenAI-format chunk from GLM.

        GLM may embed reasoning in:
        - Custom fields in the delta
        - A separate field at the root level
        - Special markers in the content itself

        This method needs to be adjusted based on actual GLM output format.
        """
        usage = data.get("usage")
        usage_dict = usage if isinstance(usage, dict) else None

        choices = data.get("choices", [])
        if not choices:
            # OpenAI-compatible providers send a final usage-only chunk with
            # empty choices when stream_options.include_usage is requested.
            # Forward the usage instead of dropping it; keep it as an empty
            # content chunk so the real [DONE] marker still terminates stream.
            if usage_dict:
                return GLMStreamChunk(
                    content_type=ContentType.CONTENT,
                    content="",
                    raw_chunk=raw_line,
                    usage=usage_dict,
                )
            return None

        delta = choices[0].get("delta", {})
        finish_reason = choices[0].get("finish_reason")

        # Check for reasoning content
        # GLM-5.1 may use a custom field for reasoning
        reasoning_content = delta.get("reasoning_content") or delta.get("reasoning")

        if reasoning_content:
            return GLMStreamChunk(
                content_type=ContentType.REASONING,
                content=reasoning_content,
                raw_chunk=raw_line,
                finish_reason=finish_reason,
                usage=usage_dict,
            )

        tool_calls = delta.get("tool_calls")
        if tool_calls:
            return GLMStreamChunk(
                content_type=ContentType.TOOL_CALL,
                content="",
                raw_chunk=raw_line,
                finish_reason=finish_reason,
                tool_calls=tool_calls,
                usage=usage_dict,
            )

        # Regular content
        content = delta.get("content", "")
        if not content and not finish_reason and not usage_dict:
            return None

        # Detect if we're still in reasoning phase based on content markers
        if self.in_reasoning and content:
            # TODO: Adjust this logic based on actual GLM format
            # GLM may have markers or we need heuristics to detect reasoning end
            if self._is_reasoning_marker(content):
                return GLMStreamChunk(
                    content_type=ContentType.REASONING,
                    content=content,
                    raw_chunk=raw_line,
                    usage=usage_dict,
                )
            else:
                self.in_reasoning = False

        return GLMStreamChunk(
            content_type=ContentType.CONTENT,
            content=content,
            raw_chunk=raw_line,
            finish_reason=finish_reason,
            usage=usage_dict,
        )

    def _is_reasoning_marker(self, content: str) -> bool:
        """
        Check if content is a reasoning phase marker.

        TODO: Implement based on actual GLM-5.1 output format.
        Possible indicators:
        - Specific text markers
        - Structural patterns
        - Custom fields in the response
        """
        # Placeholder - adjust based on actual format
        reasoning_markers = ["<reasoning>", "Reasoning:", "Thinking..."]
        return any(marker in content for marker in reasoning_markers)

    async def parse_stream(
        self, response: "aiohttp.ClientResponse"
    ) -> AsyncIterator[GLMStreamChunk]:
        """
        Parse GLM streaming response into chunks.

        Args:
            response: aiohttp streaming response

        Yields:
            Parsed chunks with content type classification
        """
        async for line in response.content:
            line_text = line.decode("utf-8").strip()
            if not line_text:
                continue

            chunk = self.parse_sse_line(line_text)
            if chunk:
                yield chunk
