"""Request-ID middleware: assigns (or propagates) an X-Request-ID for
every request and exposes it via a contextvar so structured_logging's
JSONFormatter can stamp every log line emitted while handling that
request with the same ID -- the standard way to correlate a burst of
log lines back to one HTTP request without threading an explicit
parameter through every function in the call stack.
"""

import uuid
from contextvars import ContextVar, Token
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

_HEADER_NAME = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(_HEADER_NAME) or str(uuid.uuid4())
        token: Token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[_HEADER_NAME] = request_id
        return response
