"""ASGI middleware.

Written as plain ASGI (not Starlette's BaseHTTPMiddleware) so it also works with
streaming responses such as the Server-Sent Events used for live agent updates.
"""

import json
import re
import uuid

from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a client-supplied ID only if it is short and safe to put in logs.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-_.]{1,128}$")


class RequestIDMiddleware:
    """Assigns every request an ID, exposes it to logs, and returns it in a response header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode())
        candidate = incoming.decode("latin-1") if incoming else ""
        request_id = candidate if _VALID_REQUEST_ID.match(candidate) else uuid.uuid4().hex

        # Available to handlers as `request.state.request_id`.
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_ctx.reset(token)


# Interactive API docs load Swagger UI from a CDN, so they get no strict CSP.
_DOCS_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    """Adds defensive HTTP headers to every response.

    The API only returns JSON, PDFs and event streams - never HTML for a browser to
    render - so the policy can be very strict:
    - nosniff: browsers must trust our Content-Type (no "this JSON looks like HTML");
    - CSP default-src 'none' + frame-ancestors 'none': nothing may run or be framed;
    - no-referrer: URLs (which contain IDs) are never leaked to other sites;
    - Cache-Control no-store on API data: tenant data never sits in shared caches;
    - HSTS (opt-in): browsers refuse plain HTTP for this host from then on.
    """

    def __init__(self, app: ASGIApp, *, api_prefix: str, hsts: bool = False) -> None:
        self.app = app
        self.api_prefix = api_prefix
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                if not path.startswith(_DOCS_PATHS):
                    headers.setdefault(
                        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
                    )
                if path.startswith(self.api_prefix):
                    headers.setdefault("Cache-Control", "no-store")
                if self.hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects oversized request bodies with 413 before an endpoint parses them.

    JSON is parsed fully into memory, so without a cap one request with a 500 MB "script"
    could exhaust the server's RAM. File uploads (multipart) get a larger allowance; the
    upload service still enforces the exact per-file limit while streaming to disk.

    Checks the declared Content-Length up front, and also counts the bytes actually
    received (a chunked request has no Content-Length, and a client can lie about it).
    """

    def __init__(self, app: ASGIApp, *, max_json_bytes: int, max_multipart_bytes: int) -> None:
        self.app = app
        self.max_json_bytes = max_json_bytes
        self.max_multipart_bytes = max_multipart_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
        limit = (
            self.max_multipart_bytes
            if content_type.startswith("multipart/form-data")
            else self.max_json_bytes
        )

        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(scope, send, limit)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # An HTTPException passes through FastAPI's body parsing untouched
                    # and is rendered by our handler as the standard 413 envelope.
                    raise HTTPException(413, f"Request body is larger than {limit // 1024} KB.")
            return message

        await self.app(scope, counting_receive, send)

    @staticmethod
    async def _reject(scope: Scope, send: Send, limit: int) -> None:
        request_id = scope.get("state", {}).get("request_id")
        body = json.dumps(
            {
                "error": {
                    "code": "payload_too_large",
                    "message": f"Request body is larger than {limit // 1024} KB.",
                    "details": None,
                    "request_id": request_id,
                }
            }
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
