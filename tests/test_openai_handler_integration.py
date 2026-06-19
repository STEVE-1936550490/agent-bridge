"""Integration tests for the OpenAI-compatible proxy handler."""

import json

import aiohttp
import pytest
from aiohttp import web

from agent_bridge.config import Config, ServerConfig, UpstreamConfig
from agent_bridge.server import ProxyServer


async def _start_app(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    try:
        await site.start()
    except (OSError, PermissionError) as exc:
        await runner.cleanup()
        pytest.skip(f"local TCP bind unavailable in this environment: {exc}")

    sockets = site._server.sockets
    assert sockets is not None
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


async def _write_glm_stream(response: web.StreamResponse) -> None:
    chunks = [
        {"choices": [{"delta": {"reasoning_content": "thinking should be hidden"}}]},
        {"choices": [{"delta": {"content": "Hello"}}]},
        {"choices": [{"delta": {"content": " world"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    for chunk in chunks:
        await response.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
    await response.write(b"data: [DONE]\n\n")


async def _start_mock_upstream(
    seen_payloads: list[dict],
) -> tuple[web.AppRunner, str]:
    async def handle_chat(request: web.Request) -> web.StreamResponse:
        seen_payloads.append(await request.json())
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
            }
        )
        await response.prepare(request)
        await _write_glm_stream(response)
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat)
    return await _start_app(app)


async def _start_mock_tool_upstream(
    seen_payloads: list[dict],
) -> tuple[web.AppRunner, str]:
    async def handle_chat(request: web.Request) -> web.StreamResponse:
        seen_payloads.append(await request.json())
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
            }
        )
        await response.prepare(request)
        chunks = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_shell_1",
                                    "type": "function",
                                    "function": {
                                        "name": "shell",
                                        "arguments": '{"cmd"',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": ': "pwd"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]
        for chunk in chunks:
            await response.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
        await response.write(b"data: [DONE]\n\n")
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat)
    return await _start_app(app)


async def _start_proxy(upstream_base_url: str) -> tuple[web.AppRunner, str]:
    config = Config(
        upstream=UpstreamConfig(base_url=f"{upstream_base_url}/v1", api_key="test-key"),
        server=ServerConfig(host="127.0.0.1", port=0),
    )
    proxy = ProxyServer(config)
    proxy.app.on_startup.append(proxy.on_startup)
    proxy.app.on_cleanup.append(proxy.on_cleanup)
    return await _start_app(proxy.app)


@pytest.mark.asyncio
async def test_chat_completions_stream_filters_reasoning() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/chat/completions",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "stream": True,
                    "temperature": None,
                },
            ) as response:
                assert response.status == 200
                text = await response.text()

        assert "thinking should be hidden" not in text
        assert '"role": "assistant"' in text
        assert "Hello" in text
        assert " world" in text
        assert "data: [DONE]" in text
        assert seen_payloads[0]["stream"] is True
        assert "temperature" not in seen_payloads[0]
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_chat_completions_non_stream_returns_json() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/chat/completions",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "stream": False,
                },
            ) as response:
                assert response.status == 200
                payload = await response.json()

        assert payload["object"] == "chat.completion"
        assert payload["choices"][0]["message"]["content"] == "Hello world"
        assert seen_payloads[0]["stream"] is True
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_responses_stream_converts_input_and_emits_lifecycle_events() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "Say"},
                                {"type": "input_text", "text": "hello"},
                            ],
                        }
                    ],
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                text = await response.text()

        assert seen_payloads[0]["messages"] == [{"role": "user", "content": "Say hello"}]
        assert "thinking should be hidden" not in text
        assert "event: response.output_item.added" in text
        assert "event: response.output_text.delta" in text
        assert "event: response.output_text.done" in text
        assert "event: response.completed" in text
        assert "Hello world" in text
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_responses_stream_bridges_function_tools() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_tool_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": [
                        {"role": "user", "content": "run pwd"},
                        {
                            "type": "function_call_output",
                            "call_id": "call_prev",
                            "output": "/root/agent_bridge",
                        },
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "name": "shell",
                            "description": "Run a shell command",
                            "parameters": {
                                "type": "object",
                                "properties": {"cmd": {"type": "string"}},
                                "required": ["cmd"],
                            },
                        }
                    ],
                    "tool_choice": "auto",
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                text = await response.text()

        assert seen_payloads[0]["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "shell",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {"cmd": {"type": "string"}},
                        "required": ["cmd"],
                    },
                },
            }
        ]
        assert seen_payloads[0]["tool_choice"] == "auto"
        assert seen_payloads[0]["messages"][1] == {
            "role": "tool",
            "tool_call_id": "call_prev",
            "content": "/root/agent_bridge",
        }
        assert "response.function_call_arguments.delta" in text
        assert "response.function_call_arguments.done" in text
        assert '"type": "function_call"' in text
        assert '"call_id": "call_shell_1"' in text
        assert '{\\"cmd\\": \\"pwd\\"}' in text
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_structured_logs_include_request_metadata() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                headers={"X-Request-ID": "req_test_123"},
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "stream": False,
                },
            ) as response:
                assert response.status == 200
                assert response.headers["X-Request-ID"] == "req_test_123"
                await response.text()

            async with session.get(f"{proxy_url}/logs") as response:
                assert response.status == 200
                payload = await response.json()

        logs = payload["data"]
        response_log = next(log for log in logs if log["request_id"] == "req_test_123")
        assert response_log["path"] == "/v1/responses"
        assert response_log["status"] == 200
        assert response_log["model"] == "ZHIPU/GLM-5.1"
        assert response_log["client_protocol"] == "codex_responses"
        assert response_log["provider_protocol"] == "openai_chat"
        assert response_log["token_usage"]["source"] == "unavailable"
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_dashboard_serves_log_view() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{proxy_url}/dashboard") as response:
                assert response.status == 200
                text = await response.text()

        assert "AgentBridge Dashboard" in text
        assert "/logs?limit=200" in text
        assert "token" in text.lower()
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_logs_only_include_api_requests() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            for path in ("/health", "/dashboard", "/logs"):
                async with session.get(f"{proxy_url}{path}") as response:
                    assert response.status == 200
                    await response.text()

            async with session.post(
                f"{proxy_url}/v1/responses",
                headers={"X-Request-ID": "req_api_only"},
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "stream": False,
                },
            ) as response:
                assert response.status == 200
                await response.text()

            async with session.get(f"{proxy_url}/logs") as response:
                assert response.status == 200
                payload = await response.json()

        logs = payload["data"]
        assert [log["path"] for log in logs] == ["/v1/responses"]
        assert logs[0]["request_id"] == "req_api_only"
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_anthropic_messages_non_stream_returns_message() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/messages",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "max_tokens": 100,
                    "stream": False,
                },
            ) as response:
                assert response.status == 200
                payload = await response.json()

        assert seen_payloads[0]["messages"] == [{"role": "user", "content": "Say hello"}]
        assert payload["type"] == "message"
        assert payload["role"] == "assistant"
        assert payload["content"][0]["text"] == "Hello world"
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_anthropic_messages_stream_emits_events() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/messages",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": "Say hello"}],
                        }
                    ],
                    "max_tokens": 100,
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                text = await response.text()

        assert "event: message_start" in text
        assert "event: content_block_delta" in text
        assert "Hello" in text
        assert "thinking should be hidden" not in text
        assert "event: message_stop" in text
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_anthropic_messages_bridges_tools() -> None:
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_tool_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/messages",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call_prev",
                                    "content": "/root/agent_bridge",
                                },
                                {"type": "text", "text": "run pwd"},
                            ],
                        }
                    ],
                    "tools": [
                        {
                            "name": "shell",
                            "description": "Run a shell command",
                            "input_schema": {
                                "type": "object",
                                "properties": {"cmd": {"type": "string"}},
                            },
                        }
                    ],
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                text = await response.text()

        assert seen_payloads[0]["tools"][0]["function"]["name"] == "shell"
        assert seen_payloads[0]["messages"][0] == {
            "role": "tool",
            "tool_call_id": "call_prev",
            "content": "/root/agent_bridge",
        }
        assert '"type": "tool_use"' in text
        assert "input_json_delta" in text
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


async def _write_glm_stream_with_usage(response: web.StreamResponse) -> None:
    """Stream that includes a usage-only final chunk (OpenAI include_usage shape)."""
    chunks = [
        {"choices": [{"delta": {"content": "Hello"}}]},
        {"choices": [{"delta": {"content": " world"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
        },
    ]
    for chunk in chunks:
        await response.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
    await response.write(b"data: [DONE]\n\n")


async def _start_mock_upstream_with_usage(
    seen_payloads: list[dict],
) -> tuple[web.AppRunner, str]:
    async def handle_chat(request: web.Request) -> web.StreamResponse:
        seen_payloads.append(await request.json())
        response = web.StreamResponse(
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
        )
        await response.prepare(request)
        await _write_glm_stream_with_usage(response)
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat)
    return await _start_app(app)


@pytest.mark.asyncio
async def test_upstream_usage_observed_in_logs_stream() -> None:
    """When the upstream emits usage, it appears in /logs with source=upstream."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream_with_usage(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                headers={"X-Request-ID": "req_usage_stream"},
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

            async with session.get(f"{proxy_url}/logs") as response:
                assert response.status == 200
                payload = await response.json()

        logs = payload["data"]
        log = next(log for log in logs if log["request_id"] == "req_usage_stream")
        assert log["token_usage"]["source"] == "upstream"
        assert log["token_usage"]["input_tokens"] == 10
        assert log["token_usage"]["output_tokens"] == 6
        assert log["token_usage"]["total_tokens"] == 16
        # The proxy must have asked the upstream for usage.
        assert seen_payloads[0]["stream_options"]["include_usage"] is True
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_upstream_usage_observed_in_logs_non_stream() -> None:
    """Non-streaming responses also surface upstream usage in /logs."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream_with_usage(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/chat/completions",
                headers={"X-Request-ID": "req_usage_nonstream"},
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "stream": False,
                },
            ) as response:
                assert response.status == 200
                payload = await response.json()

            async with session.get(f"{proxy_url}/logs") as response:
                assert response.status == 200
                logs = (await response.json())["data"]

        log = next(log for log in logs if log["request_id"] == "req_usage_nonstream")
        assert log["token_usage"]["source"] == "upstream"
        assert log["token_usage"]["input_tokens"] == 10
        assert log["token_usage"]["output_tokens"] == 6

        # The non-streaming response body should also carry the real usage.
        assert payload["usage"]["prompt_tokens"] == 10
        assert payload["usage"]["completion_tokens"] == 6
        assert payload["usage"]["total_tokens"] == 16
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_missing_usage_stays_unavailable() -> None:
    """When the upstream never emits usage, source stays unavailable (no error)."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy(upstream_url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/chat/completions",
                headers={"X-Request-ID": "req_no_usage"},
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

            async with session.get(f"{proxy_url}/logs") as response:
                assert response.status == 200
                logs = (await response.json())["data"]

        log = next(log for log in logs if log["request_id"] == "req_no_usage")
        assert log["token_usage"]["source"] == "unavailable"
        # include_usage is still requested; the upstream just chose not to return it.
        assert seen_payloads[0]["stream_options"]["include_usage"] is True
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


from agent_bridge.config import ProviderConfig


async def _start_proxy_with_reasoning(
    upstream_base_url: str, reasoning_mode: str
) -> tuple[web.AppRunner, str]:
    """Start a proxy whose active provider uses the given reasoning_mode."""
    config = Config(
        upstream=UpstreamConfig(base_url=f"{upstream_base_url}/v1", api_key="test-key"),
        server=ServerConfig(host="127.0.0.1", port=0),
        providers={
            "test": ProviderConfig(
                base_url=f"{upstream_base_url}/v1",
                api_key="test-key",
                model="ZHIPU/GLM-5.1",
                provider_api="openai_chat",
                client_protocol="codex_responses",
                reasoning_mode=reasoning_mode,  # type: ignore[arg-type]
            )
        },
        active_provider="test",
    )
    proxy = ProxyServer(config)
    proxy.app.on_startup.append(proxy.on_startup)
    proxy.app.on_cleanup.append(proxy.on_cleanup)
    return await _start_app(proxy.app)


@pytest.mark.asyncio
async def test_reasoning_effort_high_maps_to_thinking_enabled() -> None:
    """reasoning_mode=thinking: effort high -> thinking enabled upstream."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy_with_reasoning(upstream_url, "thinking")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "reasoning": {"effort": "high"},
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

        assert seen_payloads[0]["thinking"] == {"type": "enabled"}
        assert "reasoning_effort" not in seen_payloads[0]
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_reasoning_effort_low_maps_to_thinking_disabled() -> None:
    """reasoning_mode=thinking: effort low -> thinking disabled upstream."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy_with_reasoning(upstream_url, "thinking")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "reasoning": {"effort": "low"},
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

        assert seen_payloads[0]["thinking"] == {"type": "disabled"}
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_reasoning_effort_passthrough_forwards_field() -> None:
    """reasoning_mode=passthrough: effort forwarded as reasoning_effort."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy_with_reasoning(upstream_url, "passthrough")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/chat/completions",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "reasoning_effort": "high",
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

        assert seen_payloads[0]["reasoning_effort"] == "high"
        assert "thinking" not in seen_payloads[0]
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_reasoning_mode_none_drops_effort() -> None:
    """reasoning_mode=none: no reasoning field reaches upstream."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy_with_reasoning(upstream_url, "none")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "reasoning": {"effort": "high"},
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

        assert "thinking" not in seen_payloads[0]
        assert "reasoning_effort" not in seen_payloads[0]
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_no_reasoning_field_leaves_upstream_untouched() -> None:
    """When the client sends no reasoning, nothing is added upstream."""
    seen_payloads: list[dict] = []
    upstream_runner, upstream_url = await _start_mock_upstream(seen_payloads)
    proxy_runner, proxy_url = await _start_proxy_with_reasoning(upstream_url, "thinking")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{proxy_url}/v1/responses",
                json={
                    "model": "ZHIPU/GLM-5.1",
                    "input": "Say hello",
                    "stream": True,
                },
            ) as response:
                assert response.status == 200
                await response.text()

        assert "thinking" not in seen_payloads[0]
        assert "reasoning_effort" not in seen_payloads[0]
    finally:
        await proxy_runner.cleanup()
        await upstream_runner.cleanup()
