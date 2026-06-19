"""Test GLM response parser."""

import pytest

from moma_proxy.parsers.glm import ContentType, GLMParser, GLMStreamChunk


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
