"""Authentication for HTTP transport.

Bearer token auth for remote/tunnel access. Set ``UNIFI_MCP_API_TOKEN`` env var.
Every HTTP request must include ``Authorization: Bearer <token>``.

If the env var is **unset or empty**, bearer auth is disabled — this keeps
localhost-only setups working without any configuration.
"""

from __future__ import annotations

import json
import logging
import os
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_BEARER_TOKEN: str | None = None
_BEARER_CHECKED: bool = False


def get_bearer_token() -> str | None:
    """Return the bearer token from env, or None if not configured."""
    global _BEARER_TOKEN, _BEARER_CHECKED  # noqa: PLW0603
    if _BEARER_CHECKED:
        return _BEARER_TOKEN
    _BEARER_CHECKED = True
    token = os.environ.get("UNIFI_MCP_API_TOKEN", "").strip()
    _BEARER_TOKEN = token if token else None
    return _BEARER_TOKEN


class BearerAuthMiddleware:
    """Starlette-compatible ASGI middleware for Bearer token auth."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        expected = get_bearer_token()
        if expected is None:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")

        provided = ""
        if auth_value.lower().startswith("bearer "):
            provided = auth_value[7:]

        if provided and secrets.compare_digest(provided, expected):
            await self.app(scope, receive, send)
            return

        body = json.dumps({"error": "Unauthorized"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
