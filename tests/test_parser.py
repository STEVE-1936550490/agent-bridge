"""Test GLM response parser."""

import pytest

from agent_bridge.parsers.glm import ContentType, GLMParser, GLMStreamChunk


def test_parse_empty_line():
    """Test parser skips empty lines."""
    parser = GLMParser()
    result = parser.parse_sse_line("")
    assert result is None


def test_parse_comment_line():
    """Test parser skips comment lines."""
    parser = GLMParser()
    result = parser.parse_sse_line(": comment")
    assert result is None


def test_parse_done_marker():
    """Test parser handles [DONE] marker."""
    parser = GLMParser()
    result = parser.parse_sse_line("data: [DONE]")
    assert result is not None
    assert result.content_type == ContentType.DONE
    assert result.finish_reason == "stop"


def test_parse_content_chunk():
    """Test parser handles content chunk."""
    parser = GLMParser()
    line = 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
    result = parser.parse_sse_line(line)
    assert result is not None
    assert result.content_type == ContentType.CONTENT
    assert result.content == "Hello"


def test_parse_reasoning_chunk():
    """Test parser handles reasoning content."""
    parser = GLMParser()
    line = 'data: {"choices":[{"delta":{"reasoning_content":"Thinking..."}}]}'
    result = parser.parse_sse_line(line)
    assert result is not None
    assert result.content_type == ContentType.REASONING
    assert result.content == "Thinking..."


def test_parse_tool_call_chunk():
    """Test parser handles streamed tool call chunks."""
    parser = GLMParser()
    line = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
        '"type":"function","function":{"name":"shell","arguments":"{\\"cmd\\""}}]}}]}'
    )
    result = parser.parse_sse_line(line)

    assert result is not None
    assert result.content_type == ContentType.TOOL_CALL
    assert result.tool_calls is not None
    assert result.tool_calls[0]["id"] == "call_1"


def test_parse_invalid_json():
    """Test parser handles invalid JSON."""
    parser = GLMParser()
    line = "data: {invalid json}"
    result = parser.parse_sse_line(line)
    assert result is None


def test_parse_no_choices():
    """Test parser handles chunks without choices."""
    parser = GLMParser()
    line = 'data: {"model":"glm-5.1"}'
    result = parser.parse_sse_line(line)
    assert result is None


def test_parse_usage_only_chunk():
    """A final usage-only chunk (empty choices) is forwarded, not dropped."""
    parser = GLMParser()
    line = (
        'data: {"choices":[],"usage":{"prompt_tokens":10,'
        '"completion_tokens":5,"total_tokens":15}}'
    )
    result = parser.parse_sse_line(line)
    assert result is not None
    assert result.content_type == ContentType.CONTENT
    assert result.content == ""
    assert result.usage is not None
    assert result.usage["prompt_tokens"] == 10
    assert result.usage["total_tokens"] == 15


def test_parse_chunk_with_attached_usage():
    """Usage attached to a normal content chunk is forwarded too."""
    parser = GLMParser()
    line = (
        'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}'
    )
    result = parser.parse_sse_line(line)
    assert result is not None
    assert result.content == "hi"
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage["completion_tokens"] == 2


def test_parse_empty_choices_no_usage_dropped():
    """Empty choices without usage is still dropped (no false DONE)."""
    parser = GLMParser()
    line = 'data: {"model":"glm-5.1","choices":[]}'
    result = parser.parse_sse_line(line)
    assert result is None
