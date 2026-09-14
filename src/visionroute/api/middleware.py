"""Request-scoped middleware: correlation IDs, security headers, access logs,
request body size limits."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from visionroute.config.settings import Settings
from visionroute.observability.logging import get_logger
from visionroute.observability.metrics import observe_http_request

logger = get_logger("visionroute.api.access")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # API responses are JSON; a restrictive CSP hardens error pages.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}

# Client-supplied correlation IDs are echoed and logged, so only short,
# log-safe values are accepted; anything else is replaced by a fresh UUID.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def safe_request_id(candidate: str | None) -> str:
    if candidate and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


class BodySizeLimitMiddleware:
    """Reject request bodies above ``max_bytes`` before they are buffered.

    Checks ``Content-Length`` up front and also counts streamed chunks, so
    chunked uploads without a length header cannot bypass the limit. Once the
    limit is crossed the remaining body is withheld from the application and
    whatever response it produces is replaced by a 413 (an exception raised
    from ``receive`` would be swallowed by the framework's body parser).
    """

    def __init__(
        self, app: ASGIApp, max_bytes: int, exempt_paths: frozenset[str] = frozenset()
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        # Endpoints that enforce their own, signed per-request limit.
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > self.max_bytes
            except ValueError:
                too_large = True
            if too_large:
                await _send_too_large(send)
                return

        received = 0
        exceeded = False
        rejection_sent = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal rejection_sent
            if not exceeded:
                await send(message)
                return
            if not rejection_sent:
                rejection_sent = True
                await _send_too_large(send)

        await self.app(scope, limited_receive, guarded_send)
        if exceeded and not rejection_sent:
            await _send_too_large(send)


async def _send_too_large(send: Send) -> None:
    body = json.dumps(
        {
            "error": {
                "code": "PAYLOAD_TOO_LARGE",
                "message": "İstek gövdesi izin verilen boyutu aşıyor.",
                "request_id": None,
            }
        },
        ensure_ascii=False,
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def register_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def _request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = safe_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        elapsed_ms = round(elapsed * 1000, 2)
        # Route templates keep label cardinality bounded (never raw paths).
        route = getattr(request.scope.get("route"), "path", None) or "unmatched"
        observe_http_request(request.method, route, response.status_code, elapsed)

        response.headers["X-Request-ID"] = request_id
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.environment.is_production_like:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )

        if not request.url.path.startswith("/health"):
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
        return response

    # Added last so it runs outermost: oversized bodies never reach routing.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_request_body_bytes,
        exempt_paths=frozenset({"/api/v1/storage/local/objects"}),
    )
