"""Async HTTP server for MOMA proxy."""

import logging
import time
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web

from .config import Config
from .dashboard import DASHBOARD_HTML
from .handlers.openai import OpenAIHandler
from .observability import (
    APP_CONFIG,
    APP_REQUEST_LOGS,
    REQ_CLIENT_PROTOCOL,
    REQ_MODEL,
    REQ_PROVIDER_PROTOCOL,
    REQ_REQUEST_ID,
    REQ_STREAM_STATE,
    REQ_TOKEN_USAGE,
    RequestLog,
    RequestLogStore,
    TokenUsage,
    new_request_id,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@web.middleware
async def logging_middleware(request: web.Request, handler):
    """Log all incoming requests and responses."""
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    request[REQ_REQUEST_ID] = request_id
    start_time = time.time()
    logger.info(
        "request_started request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.path,
    )

    try:
        response = await handler(request)
        elapsed = time.time() - start_time
        response.headers["X-Request-ID"] = request_id
        log = RequestLog(
            request_id=request_id,
            timestamp=start_time,
            method=request.method,
            path=request.path,
            status=response.status,
            latency_ms=round(elapsed * 1000, 2),
            provider=request.app[APP_CONFIG].active_provider,
            model=request.get(REQ_MODEL, request.app[APP_CONFIG].default_model),
            endpoint=request.path,
            client_protocol=request.get(REQ_CLIENT_PROTOCOL),
            provider_protocol=request.get(REQ_PROVIDER_PROTOCOL),
            stream_state=request.get(REQ_STREAM_STATE, "complete"),
            token_usage=request.get(REQ_TOKEN_USAGE, TokenUsage()),
        )
        request.app[APP_REQUEST_LOGS].append(log)
        logger.info("request_completed %s", log.to_dict())
        return response
    except Exception as e:
        elapsed = time.time() - start_time
        log = RequestLog(
            request_id=request_id,
            timestamp=start_time,
            method=request.method,
            path=request.path,
            status=500,
            latency_ms=round(elapsed * 1000, 2),
            provider=request.app[APP_CONFIG].active_provider,
            model=request.get(REQ_MODEL, request.app[APP_CONFIG].default_model),
            endpoint=request.path,
            client_protocol=request.get(REQ_CLIENT_PROTOCOL),
            provider_protocol=request.get(REQ_PROVIDER_PROTOCOL),
            stream_state=request.get(REQ_STREAM_STATE, "error"),
            error=str(e),
        )
        request.app["request_logs"].append(log)
        logger.error("request_failed %s", log.to_dict())
        raise


class ProxyServer:
    """Main proxy server handling requests."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.app = web.Application(middlewares=[logging_middleware])
        self.app[APP_CONFIG] = config
        self.app[APP_REQUEST_LOGS] = RequestLogStore()
        self.session: aiohttp.ClientSession | None = None
        self.openai_handler = OpenAIHandler(config)

        # Setup routes
        self.app.router.add_route("POST", "/v1/chat/completions", self.handle_chat)
        self.app.router.add_route("POST", "/v1/completions", self.handle_completions)
        self.app.router.add_route("POST", "/v1/responses", self.handle_responses)
        self.app.router.add_route("POST", "/v1/messages", self.handle_anthropic_messages)
        self.app.router.add_route("GET", "/v1/models", self.handle_models)
        self.app.router.add_route("GET", "/health", self.handle_health)
        self.app.router.add_route("GET", "/logs", self.handle_logs)
        self.app.router.add_route("GET", "/dashboard", self.handle_dashboard)

    async def handle_chat(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/chat/completions endpoint."""
        return await self.openai_handler.handle_chat_completions(request, self.session)

    async def handle_completions(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/completions endpoint."""
        return await self.openai_handler.handle_completions(request, self.session)

    async def handle_responses(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/responses endpoint."""
        return await self.openai_handler.handle_responses(request, self.session)

    async def handle_anthropic_messages(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/messages endpoint."""
        return await self.openai_handler.handle_anthropic_messages(request, self.session)

    async def handle_models(self, request: web.Request) -> web.Response:
        """Handle /v1/models endpoint - return model metadata."""
        return web.json_response(
            {
                "object": "list",
                "data": [
                    {
                        "id": self.config.default_model,
                        "object": "model",
                        "created": 1700000000,
                        "owned_by": "openai",  # Use openai for compatibility
                    }
                ],
            }
        )

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def handle_logs(self, request: web.Request) -> web.Response:
        """Return recent structured request logs."""
        raw_limit = request.query.get("limit")
        limit = int(raw_limit) if raw_limit and raw_limit.isdigit() else 100
        return web.json_response(
            {
                "object": "list",
                "data": self.app[APP_REQUEST_LOGS].list(limit=limit),
            }
        )

    async def handle_dashboard(self, request: web.Request) -> web.Response:
        """Return the local dashboard HTML."""
        return web.Response(text=DASHBOARD_HTML, content_type="text/html")

    async def on_startup(self, app: web.Application) -> None:
        """Initialize resources on startup."""
        self.session = aiohttp.ClientSession()
        logger.info(f"Proxy server starting on {self.config.server.host}:{self.config.server.port}")

    async def on_cleanup(self, app: web.Application) -> None:
        """Cleanup resources on shutdown."""
        if self.session:
            await self.session.close()
        logger.info("Proxy server shutdown complete")


def run_server(config: Config) -> None:
    """Run the proxy server."""
    server = ProxyServer(config)
    server.app.on_startup.append(server.on_startup)
    server.app.on_cleanup.append(server.on_cleanup)

    web.run_app(
        server.app,
        host=config.server.host,
        port=config.server.port,
        access_log=None,  # Disable access logging for performance
    )
