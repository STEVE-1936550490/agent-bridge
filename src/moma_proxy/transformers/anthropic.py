"""Anthropic protocol transformer (Phase 2 - TODO)."""

# TODO: Implement Anthropic/Claude Code protocol transformation
# This will handle:
# - Converting Anthropic request format to OpenAI format for upstream
# - Converting GLM responses to Anthropic streaming format
# - Including reasoning in Anthropic's thinking blocks

# Anthropic API format:
# Request:
# {
#   "model": "claude-3-opus-20240229",
#   "messages": [{"role": "user", "content": "Hello"}],
#   "max_tokens": 1024,
#   "stream": true
# }
#
# Streaming response:
# event: message_start
# data: {"type":"message_start","message":{"id":"msg_xxx","role":"assistant","content":[]}}
#
# event: content_block_start
# data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}
#
# event: content_block_delta
# data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}
#
# event: content_block_stop
# data: {"type":"content_block_stop","index":0}
#
# event: message_delta
# data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":15}}
#
# event: message_stop
# data: {"type":"message_stop"}


class AnthropicTransformer:
    """Transform between Anthropic and OpenAI protocols."""

    def __init__(self, model: str = "claude-3-opus-20240229"):
        self.model = model

    def convert_request(self, anthropic_request: dict) -> dict:
        """
        Convert Anthropic request format to OpenAI format.

        TODO: Implement request conversion
        - Map Anthropic messages to OpenAI format
        - Handle system prompts
        - Convert max_tokens to max_completion_tokens
        """
        raise NotImplementedError("Anthropic support is Phase 2")

    async def transform_stream(self, chunks):
        """
        Transform GLM chunks to Anthropic streaming format.

        TODO: Implement streaming response conversion
        - Include reasoning in thinking blocks
        - Format as Anthropic SSE events
        """
        raise NotImplementedError("Anthropic support is Phase 2")