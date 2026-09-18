"""Per-market trading calendar -- a pure, fixed-schedule function module
used to gate Live Market Mode (see live_market_mode.py) so continuous
scanning only runs while a given market is actually open, instead of
wasting provider requests and DB writes around the clock.

Tadawul's main market trades Sunday-Thursday, 10:00-15:00 Arabia
Standard Time (UTC+3, no daylight saving) -- Tadawul's own published
regular session hours. The US market (NYSE/Nasdaq) trades Monday-
Friday, 9:30 AM-4:00 PM America/New_York time (auto-handles EST/EDT,
unlike Tadawul's fixed offset). Every public function here defaults its
new `market` parameter to `Market.TADAWUL`, so every call site written
before a second market existed keeps its exact prior behavior with no
change required at the call site -- the same convention already
established by `src.market_data.validators.symbol_validator`.

Disclosed gap (both markets): this does NOT account for either
exchange's holidays (for Tadawul: Saudi National Day, Eid al-Fitr, Eid
al-Adha, and other announced closures; for the US: New Year's Day, MLK
Day, Presidents Day, Good Friday, Memorial Day, Juneteenth, Independence
Day, Labor Day, Thanksgiving, Christmas) -- no holiday calendar feed is
integrated into this platform for either market. On an actual exchange
holiday that falls on an otherwise-trading weekday, this module will
incorrectly report the market as open. Closing this gap needs either a
maintained holiday list or a live "market status" read (e.g.
SahmkClient.get_market_summary() surfaces one for Tadawul), which would
make this pure calendar check depend on network I/O -- that trade-off is
deliberately not made here, since Live Market Mode polls this module
every LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS and a per-poll network call
would defeat the point of a cheap gate. Left as a known follow-up for
both markets, not silently worked around for either.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

from src.domain.models.stock import Market

TADAWUL_TIMEZONE = timezone(timedelta(hours=3))  # Arabia Standard Time, UTC+3, no DST
# datetime.weekday(): Mon=0 .. Sun=6. Tadawul trades Sunday-Thursday.
TADAWUL_TRADING_WEEKDAYS = frozenset({6, 0, 1, 2, 3})
TADAWUL_SESSION_OPEN = time(10, 0)
TADAWUL_SESSION_CLOSE = time(15, 0)

US_TIMEZONE = ZoneInfo("America/New_York")  # NYSE/Nasdaq -- handles EST/EDT automatically
US_TRADING_WEEKDAYS = frozenset({0, 1, 2, 3, 4})  # Mon-Fri
US_SESSION_OPEN = time(9, 30)
US_SESSION_CLOSE = time(16, 0)


@dataclass(frozen=True)
class _MarketCalendarConfig:
    timezone: tzinfo
    trading_weekdays: frozenset
    session_open: time
    session_close: time


_CALENDAR_CONFIG_BY_MARKET = {
    Market.TADAWUL: _MarketCalendarConfig(
        timezone=TADAWUL_TIMEZONE,
        trading_weekdays=TADAWUL_TRADING_WEEKDAYS,
        session_open=TADAWUL_SESSION_OPEN,
        session_close=TADAWUL_SESSION_CLOSE,
    ),
    Market.US: _MarketCalendarConfig(
        timezone=US_TIMEZONE,
        trading_weekdays=US_TRADING_WEEKDAYS,
        session_open=US_SESSION_OPEN,
        session_close=US_SESSION_CLOSE,
    ),
}


def _to_market_time(now: Optional[datetime], market: Market) -> datetime:
    config = _CALENDAR_CONFIG_BY_MARKET[market]
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(config.timezone)


def is_market_open(now: Optional[datetime] = None, market: Market = Market.TADAWUL) -> bool:
    """`now` may be naive (assumed UTC) or timezone-aware in any zone
    -- always converted to the given market's local time before
    comparison."""
    config = _CALENDAR_CONFIG_BY_MARKET[market]
    local = _to_market_time(now, market)
    if local.weekday() not in config.trading_weekdays:
        return False
    return config.session_open <= local.time() < config.session_close


def seconds_until_next_open(now: Optional[datetime] = None, market: Market = Market.TADAWUL) -> float:
    """0.0 if the given market is open right now. Otherwise the number
    of seconds until its next trading-day session open."""
    config = _CALENDAR_CONFIG_BY_MARKET[market]
    local = _to_market_time(now, market)
    if is_market_open(local, market):
        return 0.0

    candidate_day = local
    for _ in range(8):  # at most 2 consecutive non-trading days -- always terminates well before 8
        candidate_open = datetime.combine(candidate_day.date(), config.session_open, tzinfo=config.timezone)
        if candidate_day.weekday() in config.trading_weekdays and candidate_open > local:
            return (candidate_open - local).total_seconds()
        candidate_day = datetime.combine(
            candidate_day.date() + timedelta(days=1), time(0, 0), tzinfo=config.timezone
        )
    raise AssertionError("unreachable -- every 7-day window contains a trading day")


def seconds_until_close(now: Optional[datetime] = None, market: Market = Market.TADAWUL) -> Optional[float]:
    """None if the given market is not open right now."""
    config = _CALENDAR_CONFIG_BY_MARKET[market]
    local = _to_market_time(now, market)
    if not is_market_open(local, market):
        return None
    close_at = datetime.combine(local.date(), config.session_close, tzinfo=config.timezone)
    return (close_at - local).total_seconds()


# How long after a market's own published close to wait before asking
# a provider for that day's finalized daily bar -- gives the exchange/
# provider time to settle and publish the close print, so the once-
# daily OHLCV sync (see market_data.ingestion.config.
# get_ohlcv_sync_next_delay_seconds) doesn't fire into a not-yet-final
# bar and have to wait until the following day's run to pick it up.
OHLCV_SYNC_POST_CLOSE_BUFFER_MINUTES = 30


def seconds_until_next_ohlcv_sync(
    now: Optional[datetime] = None,
    buffer_minutes: int = OHLCV_SYNC_POST_CLOSE_BUFFER_MINUTES,
    market: Market = Market.TADAWUL,
) -> float:
    """Seconds until the next once-daily OHLCV ingestion window: the
    given market's next trading day's session close plus
    `buffer_minutes`.

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
    config = _CALENDAR_CONFIG_BY_MARKET[market]
    local = _to_market_time(now, market)
    buffer = timedelta(minutes=buffer_minutes)
    candidate_day = local
    for _ in range(8):  # at most 2 consecutive non-trading days -- always terminates well before 8
        candidate_sync_at = (
            datetime.combine(candidate_day.date(), config.session_close, tzinfo=config.timezone) + buffer
        )
        if candidate_day.weekday() in config.trading_weekdays and candidate_sync_at > local:
            return (candidate_sync_at - local).total_seconds()
        candidate_day = datetime.combine(
            candidate_day.date() + timedelta(days=1), time(0, 0), tzinfo=config.timezone
        )
    raise AssertionError("unreachable -- every 7-day window contains a trading day")


def to_tadawul_time(now: Optional[datetime] = None, market: Market = Market.TADAWUL) -> datetime:
    """Public wrapper over this module's own local-time conversion --
    used by callers that need to compare a stored UTC timestamp (e.g.
    a PriceBar row) against "today" in a given market's own calendar,
    such as deciding whether a locally-persisted daily bar is fresh
    enough to serve without an extra live provider call. Named for its
    original Tadawul-only caller; `market` defaults to `Market.TADAWUL`
    so that existing behavior is unchanged."""
    return _to_market_time(now, market)
