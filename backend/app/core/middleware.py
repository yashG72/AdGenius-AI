"""ASGI middleware.

Written as plain ASGI (not Starlette's BaseHTTPMiddleware) so it also works with
streaming responses such as the Server-Sent Events used for live agent updates.
"""

import re
import uuid

from starlette.datastructures import MutableHeaders
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
