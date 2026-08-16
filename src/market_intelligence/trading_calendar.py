"""Saudi Exchange (Tadawul) main-market trading calendar -- a pure,
fixed-schedule function module used to gate Live Market Mode (see
live_market_mode.py) so continuous scanning only runs while the
market is actually open, instead of wasting SAHMK requests and DB
writes around the clock.

Tadawul's main market trades Sunday-Thursday, 10:00-15:00 Arabia
Standard Time (UTC+3, no daylight saving) -- these are Tadawul's own
published regular session hours. This module encodes exactly that
fixed weekly schedule and nothing more.

Disclosed gap: this does NOT account for Tadawul's exchange holidays
(Saudi National Day, Eid al-Fitr, Eid al-Adha, and other announced
closures) -- no holiday calendar feed is integrated into this
platform. On an actual exchange holiday that falls on a Sunday-
Thursday, this module will incorrectly report the market as open.
Closing this gap needs either a maintained holiday list or a live
"market status" read (SahmkClient.get_market_summary() surfaces one),
which would make this pure calendar check depend on network I/O --
that trade-off is deliberately not made here, since Live Market Mode
polls this module every LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS and a
per-poll network call would defeat the point of a cheap gate. Left as
a known follow-up, not silently worked around.
"""

from datetime import datetime, time, timedelta, timezone
from typing import Optional

TADAWUL_TIMEZONE = timezone(timedelta(hours=3))  # Arabia Standard Time, UTC+3, no DST
# datetime.weekday(): Mon=0 .. Sun=6. Tadawul trades Sunday-Thursday.
TADAWUL_TRADING_WEEKDAYS = frozenset({6, 0, 1, 2, 3})
TADAWUL_SESSION_OPEN = time(10, 0)
TADAWUL_SESSION_CLOSE = time(15, 0)


def _to_tadawul_time(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(TADAWUL_TIMEZONE)


def is_market_open(now: Optional[datetime] = None) -> bool:
    """`now` may be naive (assumed UTC) or timezone-aware in any zone
    -- always converted to Tadawul local time before comparison."""
    local = _to_tadawul_time(now)
    if local.weekday() not in TADAWUL_TRADING_WEEKDAYS:
        return False
    return TADAWUL_SESSION_OPEN <= local.time() < TADAWUL_SESSION_CLOSE


def seconds_until_next_open(now: Optional[datetime] = None) -> float:
    """0.0 if the market is open right now. Otherwise the number of
    seconds until the next Sunday-Thursday 10:00 AST session start."""
    local = _to_tadawul_time(now)
    if is_market_open(local):
        return 0.0

    candidate_day = local
    for _ in range(8):  # at most 2 consecutive non-trading days (Fri/Sat) -- always terminates well before 8
        candidate_open = datetime.combine(candidate_day.date(), TADAWUL_SESSION_OPEN, tzinfo=TADAWUL_TIMEZONE)
        if candidate_day.weekday() in TADAWUL_TRADING_WEEKDAYS and candidate_open > local:
            return (candidate_open - local).total_seconds()
        candidate_day = datetime.combine(
            candidate_day.date() + timedelta(days=1), time(0, 0), tzinfo=TADAWUL_TIMEZONE
        )
    raise AssertionError("unreachable -- every 7-day window contains a Tadawul trading day")


def seconds_until_close(now: Optional[datetime] = None) -> Optional[float]:
    """None if the market is not open right now."""
    local = _to_tadawul_time(now)
    if not is_market_open(local):
        return None
    close_at = datetime.combine(local.date(), TADAWUL_SESSION_CLOSE, tzinfo=TADAWUL_TIMEZONE)
    return (close_at - local).total_seconds()


# How long after Tadawul's own published close to wait before asking
# SAHMK for that day's finalized daily bar -- gives the exchange/
# provider time to settle and publish the close print, so the once-
# daily OHLCV sync (see market_data.ingestion.config.
# get_ohlcv_sync_next_delay_seconds) doesn't fire into a not-yet-final
# bar and have to wait until the following day's run to pick it up.
OHLCV_SYNC_POST_CLOSE_BUFFER_MINUTES = 30


def seconds_until_next_ohlcv_sync(
    now: Optional[datetime] = None, buffer_minutes: int = OHLCV_SYNC_POST_CLOSE_BUFFER_MINUTES
) -> float:
    """Seconds until the next once-daily OHLCV ingestion window: the
    next Tadawul trading day's session close plus `buffer_minutes`.

    `historical_ohlcv` only ever writes ONE_DAY bars (see
    ingest_historical_ohlcv.py), which change at most once per trading
    day -- syncing more often than this is pure background-quota waste
    with zero freshness gain (real 2026-08-11 production evidence: an
    hourly cadence alone hit the 3,500/day background quota cap by
    22:03 UTC; a partial fix moved it to a fixed 6h interval, which
    still spent ~44% of the entire background budget on data that only
    changes once a day). This function is what makes the cadence
    actually once-daily and correctly timed, rather than just less
    frequent -- see get_ohlcv_sync_next_delay_seconds's own docstring
    for how it's wired into the scheduler.
    """
    local = _to_tadawul_time(now)
    buffer = timedelta(minutes=buffer_minutes)
    candidate_day = local
    for _ in range(8):  # at most 2 consecutive non-trading days (Fri/Sat) -- always terminates well before 8
        candidate_sync_at = (
            datetime.combine(candidate_day.date(), TADAWUL_SESSION_CLOSE, tzinfo=TADAWUL_TIMEZONE) + buffer
        )
        if candidate_day.weekday() in TADAWUL_TRADING_WEEKDAYS and candidate_sync_at > local:
            return (candidate_sync_at - local).total_seconds()
        candidate_day = datetime.combine(
            candidate_day.date() + timedelta(days=1), time(0, 0), tzinfo=TADAWUL_TIMEZONE
        )
    raise AssertionError("unreachable -- every 7-day window contains a Tadawul trading day")


def to_tadawul_time(now: Optional[datetime] = None) -> datetime:
    """Public wrapper over the module's own local-time conversion --
    used by callers that need to compare a stored UTC timestamp (e.g.
    a PriceBar row) against "today" in Tadawul's own calendar, such as
    deciding whether a locally-persisted daily bar is fresh enough to
    serve without an extra live provider call."""
    return _to_tadawul_time(now)
