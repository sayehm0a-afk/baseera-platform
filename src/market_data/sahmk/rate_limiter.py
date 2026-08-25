"""Process-wide rate limiter for SAHMK API calls.

SAHMK's quota is per API key -- account-wide, not per SahmkClient
instance. src.market_data.provider_factory and
fundamental_provider_factory each hold a *separate* SahmkClient
(market data vs. fundamentals), so a limiter owned by each client
individually would let the two draw independent budgets, doubling real
usage against the one account limit both actually share. This module's
`get_default_rate_limiter()` is a lazily-constructed singleton every
SahmkClient uses by default -- consistent with the `circuit_breaker=`
override pattern SahmkClient already has, so tests can still inject
their own instance instead of sharing the real singleton.

2026-08-10 production evidence: this process's own optimistic daily
counter (UTC-midnight reset, in-memory only) reported 60/4500 used
while SAHMK's real account-wide quota was already exhausted for
several more hours -- both because the counter never survives a
restart/new worker, and because it has no way to learn about a real
"you are out of budget" answer from SAHMK except by eventually hitting
the exact same wall itself. Two mechanisms close that gap without
guessing SAHMK's reset timezone:

1. Day counters (requests_used_today etc.) are mirrored into Redis
   (best-effort -- see _get_shared_redis_client) so a fresh process or
   a second worker reconciles with real cross-process usage instead of
   starting from zero.
2. record_upstream_daily_exhaustion() persists SAHMK's own real 429
   evidence (see SahmkDailyQuotaExhaustedError) as an authoritative
   "do not attempt any more requests until this instant" flag, shared
   the same way. acquire() checks it FIRST, before any local estimate
   and before any network call -- provider truth always overrides this
   limiter's own bookkeeping.

Both mechanisms degrade gracefully to this process's own in-memory
state alone when Redis is unavailable (e.g. every unit test in this
package, and any environment with no Redis configured) -- never raises
merely because Redis is unreachable.
"""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional, Tuple

import redis as redis_lib

from src.core.config import settings
from src.market_data import config as market_data_config
from src.market_data.sahmk.operation_scope import UNCLASSIFIED
from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL, LIVE_SCAN

logger = logging.getLogger(__name__)

# Redis key holding SAHMK's own real daily-exhaustion evidence (JSON:
# {"reset_at_utc": ..., "evidence": ...}), TTL'd to expire at exactly
# the reset instant SAHMK itself reported -- once it expires, GET
# naturally returns None again, no separate cleanup needed.
_UPSTREAM_EXHAUSTION_KEY = "sahmk:quota:upstream_exhausted"

# Conservative fallback hold when a 429 is recognized as a daily
# exhaustion but, unexpectedly, carries no parseable "expected
# available in N seconds" figure -- long enough to stop immediate
# re-hammering, short enough not to wrongly withhold requests for a
# whole day on incomplete evidence.
_DEFAULT_EXHAUSTION_HOLD_SECONDS = 3600

# TTL for the persisted per-day counters -- long enough to survive
# past the actual day boundary regardless of exactly when that is
# (this key is a storage partition keyed by UTC calendar date, not a
# claim about when SAHMK's own quota resets), short enough that stale
# days don't accumulate forever.
_DAY_COUNT_TTL_SECONDS = 2 * 24 * 3600

# P0 remediation (independent PR #99 audit, P1 finding #4): atomic
# check-and-increment for the daily quota admission decision.
#
# Before this script existed, acquire() read this process's own
# Redis-reconciled day_count (_roll_day_window_locked), decided
# admission against it LOCALLY, and only then incremented Redis via a
# separate HINCRBY -- a classic non-atomic check-then-act. Under real
# concurrent multi-process load (the actual Gunicorn --workers topology
# this limiter is designed for), two workers can each read a
# still-valid day_count, both independently conclude "admit," and both
# increment -- overspending the true daily cap by a small amount before
# either worker's own next read would have caught it. Reproduced
# empirically: 8 real OS processes racing a shared real Redis instance
# overspent max_per_day by 1 in 3 of 8 trials; reserve *partitions*
# never leaked in any trial (this script closes the remaining gap).
#
# A single EVAL is atomic on the Redis server (Redis's command
# execution is single-threaded) -- reading the current total AND
# deciding admission AND incrementing all happen as one indivisible
# step, so no interleaving between two callers is possible, without
# introducing a separate distributed lock. This mirrors the exact same
# three-cutoff logic acquire()'s own local fallback still implements
# (kept, unchanged, for when Redis is unavailable -- see
# _atomic_admit_and_increment's own docstring).
_ATOMIC_ADMIT_LUA_SCRIPT = """
local total = tonumber(redis.call('HGET', KEYS[1], 'total') or '0')
local max_per_day = tonumber(ARGV[1])
local reserved_critical = tonumber(ARGV[2])
local reserved_live_scan = tonumber(ARGV[3])
local priority = ARGV[4]
local priority_field = ARGV[5]
local ttl = tonumber(ARGV[6])
local operation_field = ARGV[7]

if total >= max_per_day then
    return {0, 'daily_cap', total}
end

local critical_cutoff = max_per_day - reserved_critical
if (priority == 'background' or priority == 'live_scan') and reserved_critical > 0 and total >= critical_cutoff then
    return {0, 'critical_reserve', total}
end

local live_scan_cutoff = critical_cutoff - reserved_live_scan
if priority == 'background' and reserved_live_scan > 0 and total >= live_scan_cutoff then
    return {0, 'live_scan_reserve', total}
end

redis.call('HINCRBY', KEYS[1], 'total', 1)
redis.call('HINCRBY', KEYS[1], priority_field, 1)
redis.call('EXPIRE', KEYS[1], ttl)
redis.call('HINCRBY', KEYS[2], operation_field, 1)
redis.call('EXPIRE', KEYS[2], ttl)
return {1, 'admitted', total + 1}
"""


def _operation_key(endpoint: Optional[str], subsystem: Optional[str]) -> str:
    """Compound "subsystem:endpoint" key -- e.g. "market_scan:quote",
    "ingestion:ohlcv", "stock_detail:quote", "unclassified:dividends".
    Two independent dimensions in one string (see operation_scope.py's
    module docstring for why they're not collapsed into one at the
    source): a report can recover either half by splitting on the first
    ":", or read the whole key for the exact (subsystem, endpoint) pair."""
    return f"{subsystem or UNCLASSIFIED}:{endpoint or 'other'}"


class SahmkRateLimitExceededError(Exception):
    """Raised when the configured daily quota is already spent for
    today (UTC). Fails fast rather than sleeping for up to 24h --
    callers (an ingestion job) should treat this as "stop for today,"
    not retry."""


class SahmkQuotaReservedForCriticalError(SahmkRateLimitExceededError):
    """Raised instead of SahmkRateLimitExceededError when a
    priority=BACKGROUND or priority=LIVE_SCAN caller's request would
    dip into the portion of today's daily quota reserved for
    priority=CRITICAL callers (live Decision Engine / market-scan quote
    lookups, active-signal and pending-outcome tracking). The daily
    quota itself is not exhausted -- only the part of it non-critical
    work is allowed to spend. Callers (ingestion jobs, admin
    diagnostics, the recurrent live-scan scheduler) should treat this
    exactly like SahmkRateLimitExceededError ("stop this work for
    today"), which is why it subclasses it -- existing except
    SahmkRateLimitExceededError handlers keep working unchanged."""


class SahmkQuotaReservedForLiveScanError(SahmkRateLimitExceededError):
    """Raised instead of SahmkRateLimitExceededError when a
    priority=BACKGROUND caller's request would dip into the portion of
    today's daily quota reserved for priority=LIVE_SCAN callers (the
    recurrent live-scan scheduler -- see
    src.market_intelligence.recurrent_live_scan). Sits strictly between
    SahmkQuotaReservedForCriticalError's reserve and ordinary background
    capacity: routine ingestion (symbols/historical_ohlcv/fundamentals/
    dividends) and any other BACKGROUND-priority caller may never spend
    the requests set aside for live scanning, even on a day ingestion
    would otherwise have plenty of quota left. Subclasses
    SahmkRateLimitExceededError for the same reason
    SahmkQuotaReservedForCriticalError does -- every existing `except
    SahmkRateLimitExceededError` handler (is_quota_exhausted_for_today,
    sleep_if_rate_limited) keeps working unchanged."""


class SahmkUpstreamQuotaExhaustedError(SahmkRateLimitExceededError):
    """Raised by acquire() when SAHMK itself has already told this
    integration (via a real 429 -- see SahmkDailyQuotaExhaustedError in
    sahmk/exceptions.py) that today's account-wide quota is exhausted,
    and the evidence-based reset time hasn't passed yet. Checked BEFORE
    any local optimistic day_count and before any network call --
    provider truth always overrides this limiter's own estimate.
    Subclasses SahmkRateLimitExceededError so every existing caller
    written against that type (is_quota_exhausted_for_today(),
    sleep_if_rate_limited()) keeps working unchanged."""

    def __init__(self, message: str, *, reset_at_utc: datetime, evidence: Optional[str] = None):
        super().__init__(message)
        self.reset_at_utc = reset_at_utc
        self.evidence = evidence


_shared_redis_client: "Optional[redis_lib.Redis]" = None
_shared_redis_client_attempted = False


def _get_shared_redis_client() -> "Optional[redis_lib.Redis]":
    """Lazily constructs a Redis client from settings.redis_dsn once
    per process, or returns None if that isn't possible (no Redis
    configured/reachable at all) -- constructing the client itself
    doesn't connect eagerly, so a genuinely down Redis is still
    discovered per-call, by whichever caller wraps its own get/incr/
    setex in try/except, not here. Every unit test in this package
    constructs its own SahmkRateLimiter with no Redis available at
    all; this function returning None is the expected, tested path
    for that case, not an error."""
    global _shared_redis_client, _shared_redis_client_attempted
    if not _shared_redis_client_attempted:
        _shared_redis_client_attempted = True
        try:
            _shared_redis_client = redis_lib.Redis.from_url(
                settings.redis_dsn, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
            )
        except Exception as exc:
            logger.warning(
                "SahmkRateLimiter: could not construct a Redis client (%s) -- quota state will "
                "only be tracked in this process's own memory, not shared across workers/restarts.",
                exc,
            )
            _shared_redis_client = None
    return _shared_redis_client


class SahmkRateLimiter:
    """Sliding-window limiter: at most `max_per_minute` acquire() calls
    complete in any trailing 60s window. If `max_per_day` is set,
    acquire() also refuses (raising SahmkRateLimitExceededError) once
    that many calls have been made since the last UTC midnight.

    If `reserved_for_critical` is also set, it carves out the last
    `reserved_for_critical` requests of each day's `max_per_day` budget
    for priority=CRITICAL callers only (see request_priority.py):
    once `day_count >= max_per_day - reserved_for_critical`, a
    priority=BACKGROUND or priority=LIVE_SCAN acquire() raises
    SahmkQuotaReservedForCriticalError instead of proceeding, while
    priority=CRITICAL acquire() keeps working until the full
    `max_per_day` is reached. This is what keeps a historical backfill,
    an admin diagnostic, or a live-scan cycle from spending the quota
    active-signal/pending-outcome tracking needs later the same day.

    If `reserved_for_live_scan` is also set, it carves out a further
    `reserved_for_live_scan` requests immediately below the critical
    reserve, for priority=LIVE_SCAN (and priority=CRITICAL) callers
    only: once `day_count >= max_per_day - reserved_for_critical -
    reserved_for_live_scan`, a priority=BACKGROUND acquire() raises
    SahmkQuotaReservedForLiveScanError instead of proceeding. This is
    the P0 quota-architecture fix: routine ingestion and every other
    BACKGROUND-priority caller can never starve the recurrent live-scan
    scheduler of its own reserve, even on a day ingestion would
    otherwise have plenty of "background" quota left to spend. The two
    reserves stack (critical is always the innermost, most-protected
    slice; live-scan sits just outside it), so
    `reserved_for_critical + reserved_for_live_scan` must not exceed
    `max_per_day`.
    """

    def __init__(
        self,
        max_per_minute: int,
        max_per_day: Optional[int] = None,
        reserved_for_critical: Optional[int] = None,
        reserved_for_live_scan: Optional[int] = None,
        redis_client: "Optional[redis_lib.Redis]" = None,
    ):
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        if max_per_day is not None and max_per_day <= 0:
            raise ValueError("max_per_day must be positive if set")
        # These remain hard construction errors -- they indicate a
        # genuine programming/config mistake (a reserve set without a
        # cap to reserve from, or a negative value), never a real-world
        # "the upstream quota changed" scenario, so failing loudly here
        # is correct and does not need fail-safe clamping.
        if reserved_for_critical is not None:
            if max_per_day is None:
                raise ValueError("reserved_for_critical requires max_per_day to be set")
            if reserved_for_critical < 0:
                raise ValueError("reserved_for_critical must not be negative")
        if reserved_for_live_scan is not None:
            if max_per_day is None:
                raise ValueError("reserved_for_live_scan requires max_per_day to be set")
            if reserved_for_live_scan < 0:
                raise ValueError("reserved_for_live_scan must not be negative")

        # P0 remediation (independent PR #99 audit, P1 finding #1):
        # reserved_for_critical + reserved_for_live_scan exceeding
        # max_per_day used to raise ValueError out of this constructor
        # -- including out of the process-wide get_default_rate_limiter()
        # singleton every SahmkClient call depends on. That is a crash,
        # not a degradation: a plausible real-world reconfiguration
        # (SAHMK_MAX_REQUESTS_PER_DAY lowered to reflect a newly
        # discovered, smaller real quota -- exactly the pattern that has
        # repeated multiple times for this integration -- without
        # proportionally lowering the reserve env vars) would take down
        # SAHMK access application-wide on the very next construction.
        #
        # Fail-safe instead: clamp, preserving critical capacity first
        # (the highest-priority protection), then live-scan, with
        # background absorbing whatever is left (down to zero, never
        # negative). This can never let a lower priority exceed its
        # intended ceiling -- it only ever shrinks reserves to fit, so
        # background can only end up MORE restricted than configured,
        # never less. A clamp is logged as a warning (observability),
        # never silent.
        clamped_critical = reserved_for_critical or 0
        clamped_live_scan = reserved_for_live_scan or 0
        if max_per_day is not None:
            if clamped_critical > max_per_day:
                logger.warning(
                    "SahmkRateLimiter: configured reserved_for_critical (%d) exceeds "
                    "max_per_day (%d) -- clamping to %d to fail safe instead of refusing "
                    "to construct. Fix SAHMK_RESERVED_FOR_CRITICAL_REQUESTS_PER_DAY.",
                    clamped_critical, max_per_day, max_per_day,
                )
                clamped_critical = max_per_day
            if clamped_critical + clamped_live_scan > max_per_day:
                safe_live_scan = max(0, max_per_day - clamped_critical)
                logger.warning(
                    "SahmkRateLimiter: configured reserved_for_critical + "
                    "reserved_for_live_scan (%d + %d = %d) exceeds max_per_day (%d) -- "
                    "clamping reserved_for_live_scan to %d (critical capacity preserved "
                    "first) to fail safe instead of refusing to construct. Fix "
                    "SAHMK_RESERVED_FOR_LIVE_SCAN_REQUESTS_PER_DAY and/or "
                    "SAHMK_MAX_REQUESTS_PER_DAY.",
                    clamped_critical, clamped_live_scan, clamped_critical + clamped_live_scan,
                    max_per_day, safe_live_scan,
                )
                clamped_live_scan = safe_live_scan

        self._max_per_minute = max_per_minute
        self._max_per_day = max_per_day
        self._reserved_for_critical = clamped_critical
        self._reserved_for_live_scan = clamped_live_scan
        self._minute_window: Deque[float] = deque()
        self._day_key: Optional[str] = None
        self._day_count = 0
        self._background_count = 0
        self._live_scan_count = 0
        self._critical_count = 0
        # Per-operation breakdown (see _operation_key) for the SAME day
        # window as the counters above -- reset together in
        # _roll_day_window_locked, never tracked separately.
        self._operation_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        # Explicit override (tests) short-circuits the lazy shared
        # singleton entirely -- None here still means "use the shared
        # one," not "no Redis," which is what makes the shared
        # singleton testable via monkeypatching it directly.
        self._redis_override = redis_client
        # In-process fallback for upstream-exhaustion evidence, used
        # only when Redis is unavailable -- still correct within this
        # one process (which is exactly the case every unit test here
        # runs under), just not shared across workers.
        self._local_upstream_reset_at: Optional[datetime] = None
        self._local_upstream_evidence: Optional[str] = None

    def _redis(self) -> "Optional[redis_lib.Redis]":
        return self._redis_override if self._redis_override is not None else _get_shared_redis_client()

    def _atomic_admit_and_increment(
        self, priority: str, operation_key: str, day_key: str
    ) -> "Optional[Tuple[bool, str]]":
        """Atomically decides admission AND increments Redis in one
        indivisible step (see _ATOMIC_ADMIT_LUA_SCRIPT's own docstring
        for the race this closes). Returns (admitted, reason) when the
        check was actually performed against real Redis -- `reason` is
        'admitted' on success, or one of 'daily_cap'/'critical_reserve'/
        'live_scan_reserve' on refusal. Returns None (never raises) when
        Redis is unavailable or the script itself fails for any reason
        -- callers must treat None as "fall back to the existing
        local-only check-then-act logic," exactly the same degradation
        every other Redis-dependent path in this class already uses."""
        client = self._redis()
        if client is None:
            return None
        priority_field = "background" if priority == BACKGROUND else ("live_scan" if priority == LIVE_SCAN else "critical")
        try:
            result = client.eval(
                _ATOMIC_ADMIT_LUA_SCRIPT,
                2,
                self._redis_day_hash_key(day_key),
                self._redis_operation_hash_key(day_key),
                str(self._max_per_day),
                str(self._reserved_for_critical),
                str(self._reserved_for_live_scan),
                priority,
                priority_field,
                str(_DAY_COUNT_TTL_SECONDS),
                operation_key,
            )
            admitted = bool(int(result[0]))
            reason = result[1].decode() if isinstance(result[1], bytes) else str(result[1])
            return admitted, reason
        except Exception:
            logger.warning(
                "SahmkRateLimiter: atomic Redis admission check failed -- falling back to "
                "this process's own local-only tracking for this request.",
                exc_info=True,
            )
            return None

    async def acquire(
        self,
        priority: str = CRITICAL,
        endpoint: Optional[str] = None,
        subsystem: Optional[str] = None,
    ) -> None:
        """Blocks (sleeping, never busy-waiting) until a slot is free
        under the per-minute window, then reserves it. Raises
        immediately -- never sleeps -- if SAHMK's own real evidence
        says today's quota is already exhausted, or if the daily quota
        (or, for a priority=BACKGROUND caller, the background-available
        portion of it) is already spent per this limiter's own
        tracking.

        `endpoint` (quote/ohlcv/fundamentals/...) and `subsystem`
        (stock_detail/market_scan/portfolio/ingestion/admin_diagnostics/
        None) are optional, additive accounting dimensions -- see
        operation_scope.py's module docstring -- recorded once the slot
        is actually reserved, for per-operation SAHMK usage reporting
        (get_status()'s `by_operation`). Never gate anything: an
        unclassified call (both None) is still counted, just under
        "unclassified:other"."""
        exhaustion = self._read_upstream_exhaustion()
        if exhaustion is not None:
            raise SahmkUpstreamQuotaExhaustedError(
                "SAHMK's real daily quota is confirmed exhausted (evidence: "
                f"{exhaustion['evidence']!r}) -- refusing further requests until "
                f"{exhaustion['reset_at'].isoformat()}.",
                reset_at_utc=exhaustion["reset_at"],
                evidence=exhaustion["evidence"],
            )

        async with self._lock:
            self._roll_day_window_locked()
            operation_key = _operation_key(endpoint, subsystem)

            # P0 remediation (independent PR #99 audit, P1 finding #4):
            # when Redis is reachable and a daily cap is configured, the
            # admission decision AND the increment happen as one atomic
            # Redis-side operation (_ATOMIC_ADMIT_LUA_SCRIPT) -- this is
            # what actually closes the cross-process race the audit
            # reproduced; everything below this point stays local-only
            # bookkeeping (mirrored into this process's own counters for
            # get_status(), never re-persisted to Redis for this same
            # request). `atomic_result` is None when there is no daily
            # cap to protect (max_per_day is None -- nothing to admit
            # against) or Redis is unavailable, in which case the
            # unchanged pre-existing local-only check-then-act logic
            # below is the fallback, exactly as before this remediation.
            atomic_result: Optional[Tuple[bool, str]] = None
            if self._max_per_day is not None:
                atomic_result = self._atomic_admit_and_increment(priority, operation_key, self._day_key)

            if atomic_result is not None:
                admitted, reason = atomic_result
                if not admitted:
                    if reason == "critical_reserve":
                        raise SahmkQuotaReservedForCriticalError(
                            f"SAHMK daily quota: only the last {self._reserved_for_critical} of "
                            f"{self._max_per_day} today's requests remain, reserved for "
                            f"live-market-critical operations -- refusing this {priority} request."
                        )
                    if reason == "live_scan_reserve":
                        raise SahmkQuotaReservedForLiveScanError(
                            f"SAHMK daily quota: only the last {self._reserved_for_live_scan} of "
                            f"{self._max_per_day - self._reserved_for_critical} background-eligible "
                            "requests remain, reserved for the recurrent live-scan scheduler -- "
                            "refusing this background request."
                        )
                    raise SahmkRateLimitExceededError(
                        f"SAHMK daily request quota ({self._max_per_day}) already reached for today (UTC)."
                    )
                # Admitted -- Redis already incremented atomically.
                # Mirror into this process's own local counters (used by
                # get_status()'s local view) WITHOUT calling
                # _persist_day_counts_increment, which would double-count
                # against the Redis total the Lua script already bumped.
                self._day_count += 1
                if priority == BACKGROUND:
                    self._background_count += 1
                elif priority == LIVE_SCAN:
                    self._live_scan_count += 1
                else:
                    self._critical_count += 1
                self._operation_counts[operation_key] = self._operation_counts.get(operation_key, 0) + 1
            else:
                # Redis unavailable, or no daily cap configured -- the
                # original, unchanged local-only check-then-act logic.
                # Not cross-process-race-free (see the module docstring
                # for the disclosed, pre-existing degradation), but
                # correct within this one process, which is the best
                # achievable without Redis as a shared source of truth.
                if self._max_per_day is not None and self._day_count >= self._max_per_day:
                    raise SahmkRateLimitExceededError(
                        f"SAHMK daily request quota ({self._max_per_day}) already reached for today (UTC)."
                    )
                # Two nested cutoffs, most-protected first: the critical
                # cutoff blocks BACKGROUND and LIVE_SCAN alike; the
                # live-scan cutoff (strictly inside the critical one)
                # blocks only BACKGROUND. CRITICAL is never blocked by
                # either -- only by the absolute max_per_day check above.
                if self._max_per_day is not None:
                    critical_cutoff = self._max_per_day - self._reserved_for_critical
                    if (
                        priority in (BACKGROUND, LIVE_SCAN)
                        and self._reserved_for_critical > 0
                        and self._day_count >= critical_cutoff
                    ):
                        raise SahmkQuotaReservedForCriticalError(
                            f"SAHMK daily quota: only the last {self._reserved_for_critical} of "
                            f"{self._max_per_day} today's requests remain, reserved for "
                            f"live-market-critical operations -- refusing this {priority} request."
                        )
                    live_scan_cutoff = critical_cutoff - self._reserved_for_live_scan
                    if (
                        priority == BACKGROUND
                        and self._reserved_for_live_scan > 0
                        and self._day_count >= live_scan_cutoff
                    ):
                        raise SahmkQuotaReservedForLiveScanError(
                            f"SAHMK daily quota: only the last {self._reserved_for_live_scan} of "
                            f"{self._max_per_day - self._reserved_for_critical} background-eligible "
                            "requests remain, reserved for the recurrent live-scan scheduler -- "
                            "refusing this background request."
                        )

            while True:
                now = time.monotonic()
                while self._minute_window and now - self._minute_window[0] >= 60.0:
                    self._minute_window.popleft()
                if len(self._minute_window) < self._max_per_minute:
                    break
                wait_seconds = 60.0 - (now - self._minute_window[0])
                logger.info(
                    "SAHMK rate limiter: %d/%d requests used in the last minute -- waiting %.2fs.",
                    len(self._minute_window),
                    self._max_per_minute,
                    wait_seconds,
                )
                await asyncio.sleep(max(wait_seconds, 0.01))

            self._minute_window.append(time.monotonic())

            if atomic_result is None:
                # Local-only path: increment local counters AND
                # best-effort persist to Redis (unchanged pre-existing
                # behavior -- _persist_day_counts_increment itself
                # already degrades gracefully if Redis is unreachable).
                self._day_count += 1
                if priority == BACKGROUND:
                    self._background_count += 1
                elif priority == LIVE_SCAN:
                    self._live_scan_count += 1
                else:
                    self._critical_count += 1
                self._operation_counts[operation_key] = self._operation_counts.get(operation_key, 0) + 1
                self._persist_day_counts_increment(priority, operation_key)

    def record_upstream_daily_exhaustion(
        self, *, retry_after_seconds: Optional[float], raw_message: str
    ) -> None:
        """Persists SAHMK's own real, evidence-based daily-quota
        exhaustion so acquire() -- in this process AND every other
        worker/deployment sharing the same Redis -- refuses further
        requests until the reset time SAHMK itself reported, instead
        of each process independently discovering the same exhaustion
        via its own wasted request.

        Deliberately never assumes a timezone or fixed reset schedule:
        the hold duration comes directly from SAHMK's own "Expected
        available in N seconds" figure (parsed in sahmk/client.py). A
        conservative fixed fallback is used only if that figure was
        missing from the response.
        """
        ttl_seconds = (
            int(retry_after_seconds)
            if retry_after_seconds is not None and retry_after_seconds > 0
            else _DEFAULT_EXHAUSTION_HOLD_SECONDS
        )
        reset_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._local_upstream_reset_at = reset_at
        self._local_upstream_evidence = raw_message
        logger.warning(
            "SahmkRateLimiter: recording SAHMK's real daily-quota exhaustion -- refusing further "
            "requests until %s (evidence: %r).",
            reset_at.isoformat(),
            raw_message,
        )
        client = self._redis()
        if client is None:
            return
        try:
            payload = json.dumps({"reset_at_utc": reset_at.isoformat(), "evidence": raw_message})
            client.set(_UPSTREAM_EXHAUSTION_KEY, payload, ex=ttl_seconds)
        except Exception:
            logger.warning(
                "SahmkRateLimiter: failed to persist upstream daily-quota-exhaustion evidence to "
                "Redis -- this process still honors it, but other workers/a restart will not "
                "until they independently hit the same 429.",
                exc_info=True,
            )

    def _read_upstream_exhaustion(self) -> Optional[Dict[str, object]]:
        client = self._redis()
        if client is not None:
            try:
                raw = client.get(_UPSTREAM_EXHAUSTION_KEY)
                if not raw:
                    return None  # Redis reachable, key absent/expired -- authoritative "not exhausted"
                data = json.loads(raw)
                reset_at = datetime.fromisoformat(data["reset_at_utc"])
                return {"reset_at": reset_at, "evidence": data.get("evidence")}
            except Exception:
                logger.warning(
                    "SahmkRateLimiter: failed reading upstream-exhaustion state from Redis -- "
                    "falling back to this process's own last-known state.",
                    exc_info=True,
                )
        if (
            self._local_upstream_reset_at is not None
            and datetime.now(timezone.utc) < self._local_upstream_reset_at
        ):
            return {"reset_at": self._local_upstream_reset_at, "evidence": self._local_upstream_evidence}
        return None

    def _redis_day_hash_key(self, day_key: str) -> str:
        return f"sahmk:quota:day:{day_key}"

    def _redis_operation_hash_key(self, day_key: str) -> str:
        return f"sahmk:quota:day:{day_key}:ops"

    def _persist_day_counts_increment(self, priority: str, operation_key: str) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            key = self._redis_day_hash_key(self._day_key)
            if priority == BACKGROUND:
                field = "background"
            elif priority == LIVE_SCAN:
                field = "live_scan"
            else:
                field = "critical"
            pipe = client.pipeline()
            pipe.hincrby(key, "total", 1)
            pipe.hincrby(key, field, 1)
            pipe.expire(key, _DAY_COUNT_TTL_SECONDS)
            ops_key = self._redis_operation_hash_key(self._day_key)
            pipe.hincrby(ops_key, operation_key, 1)
            pipe.expire(ops_key, _DAY_COUNT_TTL_SECONDS)
            pipe.execute()
        except Exception:
            logger.debug(
                "SahmkRateLimiter: failed to persist day-count increment to Redis (this process's "
                "own count is still accurate).",
                exc_info=True,
            )

    def _read_persisted_day_counts(self, day_key: str) -> Optional[Dict[str, int]]:
        client = self._redis()
        if client is None:
            return None
        try:
            raw = client.hgetall(self._redis_day_hash_key(day_key))
            if not raw:
                return None
            return {
                "day": int(raw.get("total", 0)),
                "background": int(raw.get("background", 0)),
                "live_scan": int(raw.get("live_scan", 0)),
                "critical": int(raw.get("critical", 0)),
            }
        except Exception:
            logger.debug(
                "SahmkRateLimiter: failed reading persisted day counts from Redis.", exc_info=True
            )
            return None

    def _read_persisted_operation_counts(self, day_key: str) -> Optional[Dict[str, int]]:
        client = self._redis()
        if client is None:
            return None
        try:
            raw = client.hgetall(self._redis_operation_hash_key(day_key))
            if not raw:
                return None
            return {k: int(v) for k, v in raw.items()}
        except Exception:
            logger.debug(
                "SahmkRateLimiter: failed reading persisted per-operation counts from Redis.",
                exc_info=True,
            )
            return None

    def _roll_day_window_locked(self) -> None:
        today_key = datetime.now(timezone.utc).date().isoformat()
        if today_key != self._day_key:
            self._day_key = today_key
            self._day_count = 0
            self._background_count = 0
            self._live_scan_count = 0
            self._critical_count = 0
            self._operation_counts = {}
        # Cross-process reconciliation: when Redis is reachable, use
        # whichever is higher between this process's own view and the
        # shared persisted total -- a fresh/restarted process picks up
        # real usage other workers already made today instead of
        # wrongly believing it has the full budget to itself.
        persisted = self._read_persisted_day_counts(today_key)
        if persisted is not None:
            self._day_count = max(self._day_count, persisted["day"])
            self._background_count = max(self._background_count, persisted["background"])
            self._live_scan_count = max(self._live_scan_count, persisted.get("live_scan", 0))
            self._critical_count = max(self._critical_count, persisted["critical"])
        persisted_ops = self._read_persisted_operation_counts(today_key)
        if persisted_ops is not None:
            for key, count in persisted_ops.items():
                self._operation_counts[key] = max(self._operation_counts.get(key, 0), count)

    def get_status(self) -> Dict[str, object]:
        """Secret-free snapshot for admin/system-health diagnostics
        (never touches the network -- Redis reads here are the only
        I/O, and are best-effort/non-blocking-on-failure). Reflects
        the shared, cross-process count when Redis is reachable
        (see _roll_day_window_locked), this process's own tracked
        usage otherwise. `remaining_today`/`remaining_today_for_
        background` are forced to 0 whenever SAHMK's own real evidence
        says the account is exhausted, regardless of what the
        optimistic day_count would otherwise imply -- provider truth
        always wins over this limiter's own estimate."""
        self._roll_day_window_locked()
        exhaustion = self._read_upstream_exhaustion()
        remaining_total = (
            max(0, self._max_per_day - self._day_count) if self._max_per_day is not None else None
        )
        critical_cutoff = (
            max(0, self._max_per_day - self._reserved_for_critical)
            if self._max_per_day is not None
            else None
        )
        live_scan_cutoff = (
            max(0, critical_cutoff - self._reserved_for_live_scan)
            if critical_cutoff is not None
            else None
        )
        # "background" (unqualified, existing key -- kept for backward
        # compatibility with every caller reading it today) is the cap
        # BACKGROUND callers see: everything up to the critical reserve,
        # i.e. it still includes the live-scan reserve as far as this
        # single number goes. `remaining_today_for_live_scan` and
        # `remaining_today_for_background_after_live_scan_reserve` below
        # are the new, more precise breakdown P0 needs.
        remaining_background = (
            max(0, critical_cutoff - self._day_count) if critical_cutoff is not None else None
        )
        remaining_live_scan = (
            max(0, critical_cutoff - self._day_count) if critical_cutoff is not None else None
        )
        remaining_background_after_live_scan_reserve = (
            max(0, live_scan_cutoff - self._day_count) if live_scan_cutoff is not None else None
        )
        if exhaustion is not None and self._max_per_day is not None:
            # Only overrides an actual configured cap -- "no daily cap
            # configured" (remaining_total is None) is a distinct,
            # legitimate state that real exhaustion evidence must not
            # be allowed to mask as "0 requests remain of an unset cap."
            remaining_total = 0
            remaining_background = 0
            remaining_live_scan = 0
            remaining_background_after_live_scan_reserve = 0
        tomorrow_utc_midnight = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        return {
            "max_per_minute": self._max_per_minute,
            "max_per_day": self._max_per_day,
            "reserved_for_critical": self._reserved_for_critical,
            "reserved_for_live_scan": self._reserved_for_live_scan,
            "requests_used_today": self._day_count,
            "critical_requests_used_today": self._critical_count,
            "live_scan_requests_used_today": self._live_scan_count,
            "background_requests_used_today": self._background_count,
            # Real, measured provider calls today broken down by
            # "subsystem:endpoint" (e.g. "market_scan:quote",
            # "ingestion:ohlcv", "stock_detail:quote") -- see
            # operation_scope.py's module docstring. Tracked from
            # deployment forward only; never backfilled or estimated.
            "by_operation": dict(self._operation_counts),
            "remaining_today": remaining_total,
            # Unqualified "background" cap -- unchanged meaning from
            # before this reserve existed (everything outside the
            # critical reserve). A BACKGROUND-priority caller's actual
            # available budget is the smaller
            # remaining_today_for_background_after_live_scan_reserve.
            "remaining_today_for_background": remaining_background,
            "remaining_today_for_live_scan": remaining_live_scan,
            "remaining_today_for_background_after_live_scan_reserve": (
                remaining_background_after_live_scan_reserve
            ),
            "requests_in_last_minute": len(self._minute_window),
            "day_window_key_utc": self._day_key,
            "resets_at_utc": tomorrow_utc_midnight.isoformat(),
            "quota_shared_across_workers": self._redis() is not None,
            "upstream_confirmed_exhausted": exhaustion is not None,
            "upstream_reset_at_utc": (
                exhaustion["reset_at"].isoformat() if exhaustion is not None else None
            ),
            "upstream_exhaustion_evidence": exhaustion["evidence"] if exhaustion is not None else None,
        }

    def can_run_critical_request(self) -> bool:
        """Pure, side-effect-free budget query (no acquisition, no
        network I/O beyond get_status()'s own best-effort Redis read):
        True iff a priority=CRITICAL acquire() would not immediately
        raise for quota reasons right now. Never accounts for the
        per-minute window (that's a transient, self-resolving wait, not
        a budget refusal) -- only the daily/reserve/upstream-exhaustion
        checks acquire() itself performs before an amount is spent."""
        status = self.get_status()
        if status["upstream_confirmed_exhausted"]:
            return False
        remaining = status["remaining_today"]
        return remaining is None or remaining > 0

    def can_run_live_scan_cycle(self, estimated_cost: int) -> bool:
        """True iff `estimated_cost` more priority=LIVE_SCAN requests
        would all be accepted right now, i.e. the live-scan reserve (not
        just a single request) can cover a whole cycle. Callers (the
        recurrent live-scan scheduler) should check this once, before
        starting a cycle, not per-request -- mirrors the existing
        `_quota_allows_a_recurrent_cycle` pattern in
        recurrent_live_scan.py, now backed by a real protected reserve
        instead of only a self-imposed ceiling."""
        if estimated_cost < 0:
            raise ValueError("estimated_cost must not be negative")
        status = self.get_status()
        if status["upstream_confirmed_exhausted"]:
            return False
        remaining = status["remaining_today_for_live_scan"]
        return remaining is None or remaining >= estimated_cost

    def can_run_background_request(self) -> bool:
        """True iff a priority=BACKGROUND acquire() would not
        immediately raise for quota reasons right now -- accounts for
        BOTH the critical reserve and the live-scan reserve (the
        smaller, more precise
        remaining_today_for_background_after_live_scan_reserve), unlike
        the legacy `remaining_today_for_background` status field kept
        for backward compatibility."""
        status = self.get_status()
        if status["upstream_confirmed_exhausted"]:
            return False
        remaining = status["remaining_today_for_background_after_live_scan_reserve"]
        return remaining is None or remaining > 0

    def can_run_backfill_request(self) -> bool:
        """Historical backfill is itself BACKGROUND-priority work (see
        Section 7's DAILY_CRITICAL_REFRESH vs HISTORICAL_BACKGROUND_
        BACKFILL split) -- backfill must never preempt a bounded daily
        critical refresh, so it shares exactly BACKGROUND's own budget
        check. A distinct method (rather than callers reusing
        can_run_background_request() directly) documents backfill's
        intent at each call site and gives future policy (e.g. a
        dedicated backfill sub-reserve) one place to change."""
        return self.can_run_background_request()

    def reset(self) -> None:
        """Test-only: clears all tracked usage (in-process state only --
        does not touch Redis; tests that need a clean shared Redis
        state pass their own redis_client and clear it directly)."""
        self._minute_window.clear()
        self._day_key = None
        self._day_count = 0
        self._background_count = 0
        self._live_scan_count = 0
        self._critical_count = 0
        self._operation_counts = {}
        self._local_upstream_reset_at = None
        self._local_upstream_evidence = None


_default_rate_limiter: Optional[SahmkRateLimiter] = None


def get_default_rate_limiter() -> SahmkRateLimiter:
    """Returns the process-wide SahmkRateLimiter, constructing it from
    src.market_data.config on first use. Every SahmkClient shares this
    same instance unless a caller explicitly passes its own."""
    global _default_rate_limiter
    if _default_rate_limiter is None:
        _default_rate_limiter = SahmkRateLimiter(
            max_per_minute=market_data_config.get_sahmk_max_requests_per_minute(),
            max_per_day=market_data_config.get_sahmk_max_requests_per_day(),
            reserved_for_critical=market_data_config.get_sahmk_reserved_for_critical_requests_per_day(),
            reserved_for_live_scan=market_data_config.get_sahmk_reserved_for_live_scan_requests_per_day(),
        )
    return _default_rate_limiter


def reset_default_rate_limiter() -> None:
    """Test-only: clears the singleton so the next get_default_rate_limiter()
    call rebuilds it from the current environment/config."""
    global _default_rate_limiter
    _default_rate_limiter = None
