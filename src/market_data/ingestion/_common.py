"""Shared helpers for src.market_data.ingestion's job modules.

IngestionResult and get_or_create_stock were identically duplicated
across ingest_ohlcv.py and ingest_fundamentals.py (M2.1/M2.3) --
factored out here once, reused unchanged by those two (a
behavior-preserving refactor -- neither module's public contract or
logging text changed) and by every ingestion job added since
(symbols/historical-ohlcv/dividends). upsert_price_bar is new here (not
a refactor) -- both ingest_ohlcv.py and ingest_historical_ohlcv.py need
the identical single-bar upsert.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict

from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Stock, Timeframe
from src.market_data.sahmk.rate_limiter import (
    SahmkQuotaReservedForCriticalError,
    SahmkQuotaReservedForLiveScanError,
    SahmkRateLimitExceededError,
    SahmkUpstreamQuotaExhaustedError,
)

logger = logging.getLogger(__name__)

_MAX_RATE_LIMIT_PAUSE_SECONDS = 30.0


def is_quota_exhausted_for_today(exc: Exception) -> bool:
    """True for SahmkRateLimitExceededError and its subclass
    SahmkQuotaReservedForCriticalError (see
    src.market_data.sahmk.rate_limiter) -- both mean "today's quota (or
    the background-eligible slice of it) is spent, right now, for
    every remaining symbol in this run too," unlike every other
    exception an ingestion job catches, which is per-symbol and worth
    continuing past. A job's per-symbol loop should `break` on this,
    not keep iterating: every remaining symbol would hit the identical,
    already-known outcome at the rate limiter's acquire() call --
    before it even reaches the network -- so continuing wastes loop
    time and floods IngestionResult.errors/logs with N-1 duplicate
    entries carrying zero new information."""
    return isinstance(exc, SahmkRateLimitExceededError)


def quota_exhaustion_stop_reason(exc: Exception) -> str:
    """Maps a SahmkRateLimitExceededError (or a subclass) to the
    STOP_REASON_* constant that best describes WHY a run stopped early
    -- Section 11's observability requirement that a budget-limited
    background run must never be indistinguishable from a genuine
    failure. Order matters: the more specific subclasses are checked
    before the base class."""
    if isinstance(exc, SahmkUpstreamQuotaExhaustedError):
        return STOP_REASON_UPSTREAM_EXHAUSTED
    if isinstance(exc, SahmkQuotaReservedForLiveScanError):
        return STOP_REASON_LIVE_SCAN_RESERVE_PROTECTED
    if isinstance(exc, SahmkQuotaReservedForCriticalError):
        return STOP_REASON_CRITICAL_RESERVE_PROTECTED
    # Plain SahmkRateLimitExceededError (client-side max_per_day count
    # reached, with no more specific reserve or upstream-evidence
    # subclass): reported the same as UPSTREAM_EXHAUSTED -- both mean
    # "today's daily budget is spent, stop," which is the only
    # actionable distinction Section 11's stop-reason vocabulary draws.
    return STOP_REASON_UPSTREAM_EXHAUSTED


async def sleep_if_rate_limited(exc: Exception) -> None:
    """If `exc` carries a real, server-provided Retry-After hint
    (SahmkRateLimitError.retry_after, set once SahmkClient's own
    3-attempt retry is exhausted on a 429), sleeps for that long --
    capped at _MAX_RATE_LIMIT_PAUSE_SECONDS so a large or malformed
    value can never stall a job for an unbounded time -- before the
    caller's per-symbol loop moves on to the next symbol.

    Without this, a genuine SAHMK rate-limit response was followed
    immediately by the very next symbol's request, with nothing in any
    ingestion job actually backing off at the job level -- fine at
    ~100 symbols, but exactly the kind of gap that turns one real 429
    into dozens of consecutive symbol failures once a run covers ~400
    symbols. A no-op for any other exception (no retry_after
    attribute, or None)."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is None:
        return
    delay = min(max(float(retry_after), 0.0), _MAX_RATE_LIMIT_PAUSE_SECONDS)
    if delay > 0:
        logger.warning(
            "Rate-limited by SAHMK (retry_after=%.1fs) -- pausing %.1fs before the next symbol.",
            retry_after,
            delay,
        )
        await asyncio.sleep(delay)


# P0 SAHMK quota architecture repair (2026-08-25), Section 11
# observability: why a run ended the way it did. COMPLETED means every
# requested symbol was attempted (success or per-symbol failure, not a
# budget refusal); every other value means the run stopped early for a
# reason that is not itself a failure and must not be reported as one.
STOP_REASON_COMPLETED = "COMPLETED"
STOP_REASON_CRITICAL_RESERVE_PROTECTED = "CRITICAL_RESERVE_PROTECTED"
STOP_REASON_LIVE_SCAN_RESERVE_PROTECTED = "LIVE_SCAN_RESERVE_PROTECTED"
STOP_REASON_UPSTREAM_EXHAUSTED = "UPSTREAM_EXHAUSTED"
STOP_REASON_NO_WORK = "NO_WORK"
# PR #108 P0 remediation: a call site skipped its attempt because
# another historical_ohlcv execution (from any entry point -- the
# manual admin route, the recurring scheduler, or /full-discovery)
# already holds the shared execution lock. Never a job failure.
STOP_REASON_ALREADY_RUNNING = "ALREADY_RUNNING"


@dataclass
class IngestionResult:
    """Summary of one ingestion job run over a list of symbols."""

    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    rows_upserted: int = 0
    errors: Dict[str, str] = field(default_factory=dict)
    # A symbol counted in symbols_succeeded (no exception raised) whose
    # provider call nonetheless returned zero usable rows -- distinct
    # from `errors`, which is only ever populated on a raised exception.
    # Currently only ingest_historical_ohlcv.py populates this.
    zero_progress: Dict[str, str] = field(default_factory=dict)
    # How many of `symbols_requested` were never attempted because a
    # symbol already had today's bar (DB-first freshness check --
    # `start > today` in ingest_historical_ohlcv.py) -- zero provider
    # cost, not a failure, not a budget skip.
    symbols_skipped_fresh: int = 0
    # How many of `symbols_requested` were never attempted because the
    # run stopped early on a budget/quota refusal (see `stop_reason`)
    # before reaching them -- distinct from symbols_failed (a real
    # per-symbol provider/data error).
    symbols_skipped_budget: int = 0
    # One of the STOP_REASON_* constants above -- COMPLETED unless the
    # run ended early. Never left as None: a run that never even starts
    # (e.g. an empty symbol list) reports STOP_REASON_NO_WORK.
    stop_reason: str = STOP_REASON_COMPLETED

    @property
    def success(self) -> bool:
        return self.symbols_failed == 0 and self.symbols_requested > 0


UNCLASSIFIED_BUCKET = "UNCLASSIFIED_UNRESOLVED"
_UNCLASSIFIED_REASON = (
    "Stock row created without classified-directory confirmation "
    "(universe_policy.classify_universe never ran against this symbol); "
    "not yet verified as an eligible common equity."
)


def get_or_create_stock(session: Session, symbol: str, trusted: bool = False) -> Stock:
    """Ensures a Stock row exists for `symbol`, creating a placeholder if
    not.

    A newly created placeholder defaults to `is_active=False` /
    `instrument_bucket=UNCLASSIFIED_UNRESOLVED` -- a security must never
    silently become an ordinary tradeable Saudi equity merely because a
    Stock row exists for it. The single real authority for `is_active`
    is universe_policy.classify_universe(), applied via
    ingest_symbols.sync_symbols()'s directory-classification pass
    (src.market_intelligence.universe_policy).

    `trusted=True` is the one deliberate exception: an operator's own
    explicitly-configured INGESTION_SYMBOL_UNIVERSE seed list (see
    ingest_symbols.sync_symbols) is a curated, human-reviewed decision,
    not an unverified auto-discovered/referenced symbol, so it keeps the
    prior default-active cold-start behavior. Every other caller --
    OHLCV/fundamentals/dividends ingestion, and sync_symbols() itself for
    any symbol reached only via provider discovery -- must never make
    that trust call implicitly, which is exactly how sukuk/REIT/unknown
    instruments previously leaked into the active-equity universe as
    bare, unclassified stubs (root-caused 2026-08-08: symbols like
    6000/6003/6005-6009/6011/6563 existed as `name_en="Stock <symbol>"`
    placeholders, is_active=True by the old default, forever after)."""
    stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
    if stock is not None:
        return stock

    if trusted:
        logger.warning(
            "Creating placeholder Stock row for explicitly-configured symbol '%s' "
            "with no reference data yet (name/sector) -- trusted active by operator "
            "configuration until real reference data ingestion enriches it.",
            symbol,
        )
        stock = Stock(symbol=symbol, name_en=f"Stock {symbol}")
    else:
        logger.warning(
            "Creating UNCLASSIFIED placeholder Stock row for symbol '%s' -- "
            "is_active=False until universe_policy.classify_universe() confirms "
            "it is a real, eligible common equity.",
            symbol,
        )
        stock = Stock(
            symbol=symbol,
            name_en=f"Stock {symbol}",
            is_active=False,
            instrument_bucket=UNCLASSIFIED_BUCKET,
            exclusion_reason=_UNCLASSIFIED_REASON,
        )
    session.add(stock)
    session.flush()  # assign stock.id without committing yet
    return stock


def upsert_price_bar(session: Session, stock: Stock, data: Dict) -> bool:
    """Upserts one OHLCV bar (the shape IMarketDataProvider.get_stock_data()/
    get_historical_ohlcv() both return) keyed by (stock_id, timeframe,
    timestamp) -- the same identity PriceBar's own unique constraint
    enforces, so this is safe to call repeatedly with the same bar
    (idempotent) and safe under concurrent ingestion runs (the
    constraint is the actual backstop, this is the common-case fast
    path). Returns True if a new row was inserted, False if an existing
    one was updated -- callers use this to count rows_upserted without
    caring which case it was."""
    timestamp = datetime.fromisoformat(data["timestamp"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    existing = (
        session.query(PriceBar)
        .filter_by(stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=timestamp)
        .one_or_none()
    )

    source = data.get("source", "unknown")
    is_synthetic = data.get("is_synthetic", True)

    if existing is not None:
        existing.open = Decimal(str(data["open"]))
        existing.high = Decimal(str(data["high"]))
        existing.low = Decimal(str(data["low"]))
        existing.close = Decimal(str(data["close"]))
        existing.volume = int(data["volume"])
        existing.source = source
        existing.is_synthetic = is_synthetic
        return False

    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=timestamp,
            open=Decimal(str(data["open"])),
            high=Decimal(str(data["high"])),
            low=Decimal(str(data["low"])),
            close=Decimal(str(data["close"])),
            volume=int(data["volume"]),
            source=source,
            is_synthetic=is_synthetic,
        )
    )
    return True
