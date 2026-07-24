"""Request-ID propagation: every response carries an `X-Request-ID`
header, and every route handler can read the same value back off
`request.state.request_id` for structured logging correlation
(structured_logging already exists and is already used by main.py --
this middleware only supplies the identifier, it does not change how
logging itself works).

Honors an inbound `X-Request-ID` if the caller (e.g. an upstream
gateway) already supplies one, generating a fresh UUID4 only when
absent -- so a request traced across multiple services keeps one
consistent ID rather than getting a new one at each hop.

======================================================================
ARCHITECTURAL DECISION: raw ASGI middleware, not Starlette's
BaseHTTPMiddleware
======================================================================
Verified directly in this environment: a `BaseHTTPMiddleware` subclass
here, combined with this milestone's `@app.exception_handler(...)`
registrations (error_handlers.py), caused an exception a route raised
to be correctly caught and turned into a JSONResponse by the handler,
*and* to still propagate further up the ASGI stack afterward as an
unhandled `ExceptionGroup` -- a documented Starlette limitation of
`BaseHTTPMiddleware` (it runs the downstream app inside an internal
`anyio` task group, which does not always interoperate cleanly with
exception handlers registered elsewhere in the stack). Raw ASGI
middleware (implementing `__call__(scope, receive, send)` directly, no
task group involved) does not have this failure mode and is Starlette's
own documented alternative for exactly this situation.
"""

import uuid
from typing import Optional

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.encode("latin-1")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        inbound = headers.get(REQUEST_ID_HEADER.lower().encode("latin-1"))
        request_id = inbound.decode("latin-1") if inbound else str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (_REQUEST_ID_HEADER_BYTES, request_id.encode("latin-1"))
                ]
            await send(message)

        await self.app(scope, receive, send_wrapper)


def get_request_id(request: Request) -> Optional[str]:
    """Convenience accessor for route handlers and exception handlers --
    falls back to a fresh UUID4 only if the middleware somehow was not
    installed (defensive, should not happen in the real app), so a
    route can never crash just because it wants to read the request
    ID."""
    request_id = request.scope.get("state", {}).get("request_id")
    return request_id or str(uuid.uuid4())
