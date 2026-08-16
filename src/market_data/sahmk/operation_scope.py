"""Marks the current async call stack's SAHMK requests with the Basirah
subsystem that triggered them, for per-operation SAHMK accounting (SAHMK
quota optimization mandate, 2026-08-16): "Add proper per-operation SAHMK
accounting so future reports can show real measured provider calls by
operation."

Same contextvar pattern as request_priority.py's priority_scope, for the
same reason: one shared SahmkClient/SharedTTLCache instance is used by
every caller in the process (stock-detail route, market scan, portfolio
analysis, ingestion jobs, admin diagnostics), so a parameter threaded
through every method signature down to SahmkClient/SharedTTLCache isn't
practical -- a contextvar correctly follows one asyncio task's call stack
into those shared layers without changing any of their signatures.

Default is None ("unclassified subsystem") -- unmarked code paths are
still accounted for, just under the SAHMK-endpoint-derived category alone
(see client.py's _classify_endpoint), with no subsystem tag layered on
top. Deliberately a SEPARATE dimension from the SAHMK-endpoint category
(quote/ohlcv/fundamentals/dividends/symbols/...): both are tracked
together as a compound key (see rate_limiter.py/redis_shared_cache.py)
because they answer different questions -- "what kind of SAHMK data was
fetched" vs. "which Basirah subsystem asked for it" -- and collapsing
them would lose real information the audit mandate explicitly asked for
(e.g. distinguishing ingestion's OHLCV calls from a live market scan's
OHLCV calls).
"""

import contextlib
import contextvars
from typing import Iterator, Optional

STOCK_DETAIL = "stock_detail"
MARKET_SCAN = "market_scan"
PORTFOLIO = "portfolio"
INGESTION = "ingestion"
ADMIN_DIAGNOSTICS = "admin_diagnostics"

UNCLASSIFIED = "unclassified"

_operation_var: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "sahmk_operation", default=None
)


def get_current_operation() -> Optional[str]:
    """None means no subsystem scope is active -- callers should treat
    this as UNCLASSIFIED, not as an error."""
    return _operation_var.get()


@contextlib.contextmanager
def operation_scope(name: str) -> Iterator[None]:
    """Marks every SAHMK request/cache lookup made while this context is
    active with the Basirah subsystem `name`. Nestable: a scope's own
    value is restored on exit, not reset to None, so an inner scope wins
    for its own duration without clobbering an outer one once it exits."""
    token = _operation_var.set(name)
    try:
        yield
    finally:
        _operation_var.reset(token)
