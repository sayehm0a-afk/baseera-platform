"""In-memory, fixed-window rate limiting.

======================================================================
ARCHITECTURAL DECISION: in-memory, not Redis-backed
======================================================================
`src.core.messaging.redis_message_bus` already exists and could back a
distributed rate limiter, but Redis is not reliably available in every
environment this app runs in (confirmed repeatedly across this
project's own milestones -- `redis-cli ping` fails in this sandbox, and
the integration tests that need Redis are skipped here for exactly that
reason). Requiring Redis just to rate-limit would make the API layer
depend on infrastructure this environment cannot guarantee, and
connecting a new external service is explicitly out of this
milestone's scope. This limiter is therefore per-process, in-memory --
correct and self-contained for a single instance, and a known,
disclosed limitation for a horizontally-scaled multi-process deployment
(each process enforces its own window independently). Swapping the
storage backend for a shared one later is a contained change: only
`_RateLimiter`'s internals would need to change, not the middleware's
interface or any route.
"""

import time
from typing import Dict, Tuple

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class _RateLimiter:
    """Fixed-window counter keyed by (client_key, window_index)."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._counts: Dict[Tuple[str, int], int] = {}

    def _window_index(self, now: float) -> int:
        return int(now // self._window_seconds)

    def is_allowed(self, client_key: str, now: float = None) -> bool:  # type: ignore[assignment]
        now = now if now is not None else time.time()
        window = self._window_index(now)
        key = (client_key, window)
        count = self._counts.get(key, 0)
        if count >= self._max_requests:
            return False
        self._counts[key] = count + 1
        self._prune(window)
        return True

    def _prune(self, current_window: int) -> None:
        # Bounded memory: drop any window older than the current one --
        # a fixed window never needs more than the current window's
        # counts to make its decision.
        stale_keys = [key for key in self._counts if key[1] < current_window]
        for key in stale_keys:
            del self._counts[key]


class RateLimitMiddleware:
    """Raw ASGI middleware, not Starlette's BaseHTTPMiddleware -- see
    request_id.py's module docstring for why (the same exception-
    handler interoperability issue applies here identically)."""

    def __init__(self, app: ASGIApp, max_requests: int, window_seconds: int) -> None:
        self.app = app
        self._limiter = _RateLimiter(max_requests, window_seconds)
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_key = client[0] if client else "unknown"

        if not self._limiter.is_allowed(client_key):
            request_id = scope.get("state", {}).get("request_id")
            response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded: max {self._max_requests} "
                        f"requests per {self._window_seconds}s",
                        "request_id": request_id,
                    }
                },
                headers={"Retry-After": str(self._window_seconds)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
