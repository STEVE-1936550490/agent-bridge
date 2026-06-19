"""Test Codex transformer."""

import pytest

from agent_bridge.parsers.glm import ContentType, GLMStreamChunk
from agent_bridge.transformers.anthropic import AnthropicTransformer
from agent_bridge.transformers.codex import CodexTransformer
from agent_bridge.transformers.responses import ResponsesTransformer


def test_format_chunk():
    """Test basic chunk formatting."""
    transformer = CodexTransformer(model="glm-5.1")
    result = transformer.format_chunk("Hello")
    assert "data:" in result
    assert "glm-5.1" in result
    assert "Hello" in result


def test_format_chunk_with_finish():
    """Test chunk formatting with finish reason."""
    transformer = CodexTransformer()
    result = transformer.format_chunk("Done", finish_reason="stop")
    assert "finish_reason" in result
    assert "stop" in result


def test_format_done():
    """Test [DONE] marker formatting."""
    transformer = CodexTransformer()
    result = transformer.format_done()
    assert result == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_transform_stream():
    """Test stream transformation."""
    transformer = CodexTransformer()

    async def mock_chunks():
        yield GLMStreamChunk(ContentType.CONTENT, "Hello", "raw1")
        yield GLMStreamChunk(ContentType.REASONING, "Thinking", "raw2")
        yield GLMStreamChunk(ContentType.CONTENT, " World", "raw3")
        yield GLMStreamChunk(ContentType.DONE, "", "raw4", finish_reason="stop")

    chunks = []
    async for sse_line in transformer.transform(mock_chunks()):
        chunks.append(sse_line)

    # Should have content chunks + done marker
    assert len(chunks) >= 2
    assert "data: [DONE]" in chunks[-1]


@pytest.mark.asyncio
async def test_transform_skip_reasoning():
    """Test that reasoning is skipped by default."""
    transformer = CodexTransformer()

    async def mock_chunks():
        yield GLMStreamChunk(ContentType.REASONING, "Thinking...", "raw1")
        yield GLMStreamChunk(ContentType.CONTENT, "Answer", "raw2")
        yield GLMStreamChunk(ContentType.DONE, "", "raw3")

    chunks = []
    async for sse_line in transformer.transform(mock_chunks()):
        chunks.append(sse_line)

    # Reasoning should be skipped
    assert "Thinking" not in "".join(chunks)
    assert "Answer" in "".join(chunks)


@pytest.mark.asyncio
async def test_transform_include_reasoning():
    """Test that reasoning can be included."""
    transformer = CodexTransformer()

    async def mock_chunks():
        yield GLMStreamChunk(ContentType.REASONING, "Thinking...", "raw1")
        yield GLMStreamChunk(ContentType.CONTENT, "Answer", "raw2")
        yield GLMStreamChunk(ContentType.DONE, "", "raw3")

    chunks = []
    async for sse_line in transformer.transform(mock_chunks(), include_reasoning=True):
        chunks.append(sse_line)

    # Reasoning should be included
    assert "Thinking" in "".join(chunks)
    assert "Answer" in "".join(chunks)


@pytest.mark.asyncio
async def test_responses_transform_tool_call_stream():
    """Test Responses transformer emits function call events."""
    transformer = ResponsesTransformer()

    async def mock_chunks():
        yield GLMStreamChunk(
            ContentType.TOOL_CALL,
            "",
            "raw1",
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "shell", "arguments": '{"cmd"'},
                }
            ],
        )
        yield GLMStreamChunk(
            ContentType.TOOL_CALL,
            "",
            "raw2",
            tool_calls=[
                {
                    "index": 0,
                    "function": {"arguments": ': "pwd"}'},
                }
            ],
        )
        yield GLMStreamChunk(ContentType.DONE, "", "raw3", finish_reason="tool_calls")

    events = []
    async for sse_event in transformer.transform(mock_chunks()):
        events.append(sse_event)

    text = "".join(events)
    assert "response.output_item.added" in text
    assert "response.function_call_arguments.delta" in text
    assert "response.function_call_arguments.done" in text
    assert '"type": "function_call"' in text
    assert '"call_id": "call_123"' in text
    assert '{\\"cmd\\": \\"pwd\\"}' in text


@pytest.mark.asyncio
async def test_anthropic_transform_text_stream():
    """Test Anthropic transformer emits text lifecycle events."""
    transformer = AnthropicTransformer(model="ZHIPU/GLM-5.1")

    async def mock_chunks():
        yield GLMStreamChunk(ContentType.REASONING, "Thinking", "raw1")
        yield GLMStreamChunk(ContentType.CONTENT, "Hello", "raw2")
        yield GLMStreamChunk(ContentType.CONTENT, " world", "raw3")
        yield GLMStreamChunk(ContentType.DONE, "", "raw4")

    events = []
    async for event in transformer.transform_stream(mock_chunks()):
        events.append(event)

    text = "".join(events)
    assert "message_start" in text
    assert "content_block_start" in text
    assert "text_delta" in text
    assert "Hello" in text
    assert "Thinking" not in text
    assert "message_stop" in text


@pytest.mark.asyncio
async def test_anthropic_transform_tool_use_stream():
    """Test Anthropic transformer emits tool_use blocks."""
    transformer = AnthropicTransformer(model="ZHIPU/GLM-5.1")

    async def mock_chunks():
        yield GLMStreamChunk(
            ContentType.TOOL_CALL,
            "",
            "raw1",
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "shell", "arguments": '{"cmd"'},
                }
            ],
        )
        yield GLMStreamChunk(
            ContentType.TOOL_CALL,
            "",
            "raw2",
            tool_calls=[{"index": 0, "function": {"arguments": ': "pwd"}'}}],
        )
        yield GLMStreamChunk(ContentType.DONE, "", "raw3")

    events = []
    async for event in transformer.transform_stream(mock_chunks()):
        events.append(event)

    text = "".join(events)
    assert '"type": "tool_use"' in text
    assert '"name": "shell"' in text
    assert "input_json_delta" in text
    assert "tool_use" in text
