"""Async HTTP server for MOMA proxy."""

import logging
import time
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web

from .config import Config
from .handlers.openai import OpenAIHandler

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@web.middleware
async def logging_middleware(request: web.Request, handler):
    """Log all incoming requests and responses."""
    start_time = time.time()
    logger.info(f"--> {request.method} {request.path}")

    try:
        response = await handler(request)
        elapsed = time.time() - start_time
        logger.info(f"<-- {request.method} {request.path} {response.status} ({elapsed:.2f}s)")
        return response
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"<-- {request.method} {request.path} ERROR: {e} ({elapsed:.2f}s)")
        raise


class ProxyServer:
    """Main proxy server handling requests."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.app = web.Application(middlewares=[logging_middleware])
        self.session: aiohttp.ClientSession | None = None
        self.openai_handler = OpenAIHandler(config)

        # Setup routes
        self.app.router.add_route("POST", "/v1/chat/completions", self.handle_chat)
        self.app.router.add_route("POST", "/v1/completions", self.handle_completions)
        self.app.router.add_route("POST", "/v1/responses", self.handle_responses)
        self.app.router.add_route("GET", "/v1/models", self.handle_models)
        self.app.router.add_route("GET", "/health", self.handle_health)

    async def handle_chat(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/chat/completions endpoint."""
        return await self.openai_handler.handle_chat_completions(request, self.session)

    async def handle_completions(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/completions endpoint."""
        return await self.openai_handler.handle_completions(request, self.session)

    async def handle_responses(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/responses endpoint."""
        return await self.openai_handler.handle_responses(request, self.session)

    async def handle_models(self, request: web.Request) -> web.Response:
        """Handle /v1/models endpoint - return model metadata."""
        return web.json_response({
            "object": "list",
            "data": [
                {
                    "id": "ZHIPU/GLM-5.1",
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "openai"  # Use openai for compatibility
                }
            ]
        })

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def on_startup(self, app: web.Application) -> None:
        """Initialize resources on startup."""
        self.session = aiohttp.ClientSession()
        logger.info(
            f"Proxy server starting on {self.config.server.host}:{self.config.server.port}"
        )

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