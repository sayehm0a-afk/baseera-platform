"""Marks the current async call stack's SAHMK requests as "critical" or
"background," so the shared SahmkRateLimiter (rate_limiter.py) can
reserve part of the daily quota for live-market-critical operations
(a scan's live quote lookups) and refuse background work (ingestion
backfills, admin diagnostics) once that reserve is the only budget
left for today.

A contextvar, not a parameter threaded through every SahmkClient
method, because one SahmkClient instance is a shared, cached singleton
(see provider_factory.py) used by every caller in the process --
ingestion jobs, diagnostics routes, and live scans all share the same
client. A contextvar correctly follows one asyncio task's call stack
(including into the shared client/service/rate-limiter layers) without
changing any of their signatures.

Default priority is "critical" -- unmarked code (any route or path
this module's callers haven't been updated to wrap) keeps today's
existing behavior: it can spend the full daily budget, exactly as
before this module existed. Only code that explicitly knows it is
non-urgent background work opts into the lower priority.
"""

import contextlib
import contextvars
from typing import Iterator

CRITICAL = "critical"
BACKGROUND = "background"

_priority_var: "contextvars.ContextVar[str]" = contextvars.ContextVar(
    "sahmk_request_priority", default=CRITICAL
)


def get_current_priority() -> str:
    return _priority_var.get()


@contextlib.contextmanager
def priority_scope(priority: str) -> Iterator[None]:
    """Marks every SAHMK request made while this context is active with
    `priority` (CRITICAL or BACKGROUND). Nestable: a scope's own value
    is restored on exit, not reset to CRITICAL, so nesting
    background-inside-background (or a background job calling into a
    critical-priority helper) behaves as the innermost scope intends
    without clobbering an outer one."""
    if priority not in (CRITICAL, BACKGROUND):
        raise ValueError(f"Unknown SAHMK request priority: {priority!r}")
    token = _priority_var.set(priority)
    try:
        yield
    finally:
        _priority_var.reset(token)
