"""Unit tests for SahmkRateLimiter. Real wall-clock sleeps are avoided
throughout -- either by staying under the configured limit, or by
monkeypatching asyncio.sleep and asserting it was awaited with roughly
the expected wait duration instead of actually waiting."""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

import src.market_data.sahmk.rate_limiter as rate_limiter_module
from src.market_data.sahmk.rate_limiter import (
    SahmkQuotaReservedForCriticalError,
    SahmkRateLimitExceededError,
    SahmkRateLimiter,
    SahmkUpstreamQuotaExhaustedError,
    get_default_rate_limiter,
    reset_default_rate_limiter,
)
from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL

# Captured before the autouse fixture below ever patches the module
# attribute of the same name -- test_shared_redis_client_construction_
# failure_degrades_to_none needs the REAL implementation to exercise
# its own construction-failure handling, not the "always None" stub
# every other test in this file gets.
_REAL_GET_SHARED_REDIS_CLIENT = rate_limiter_module._get_shared_redis_client


@pytest.fixture(autouse=True)
def _no_real_shared_redis_by_default(monkeypatch):
    """Every test in this file must be isolated from any real Redis --
    a test environment that actually provisions Redis (CI does; this
    repo's local dev sandbox does not) would otherwise let quota state
    leak across tests through SahmkRateLimiter's process-wide shared
    singleton (the same one production uses), since `redis_client=None`
    on a limiter's constructor means "use the default shared client,"
    not "no Redis." 2026-08-10 production evidence: exactly this
    caused real CI failures -- one test's record_upstream_daily_
    exhaustion() call against a real Redis service persisted for the
    rest of the suite, and cross-test day-counter reconciliation picked
    up other tests' usage.

    Tests that explicitly exercise real Redis-backed sharing pass their
    own _FakeRedis instance via redis_client= (SahmkRateLimiter._redis()
    prefers that override over this patched singleton), so they are
    unaffected by this fixture."""
    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)
    yield


class _FakeRedisPipeline:
    """Minimal stand-in for redis-py's Pipeline, backed by the same
    in-memory hash store the fake client itself uses -- just enough of
    the real interface (hincrby/expire/execute) for
    SahmkRateLimiter._persist_day_counts_increment."""

    def __init__(self, hashes: dict):
        self._hashes = hashes
        self._ops = []

    def hincrby(self, key, field, amount):
        self._ops.append(("hincrby", key, field, amount))
        return self

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "hincrby":
                _, key, field, amount = op
                bucket = self._hashes.setdefault(key, {})
                bucket[field] = int(bucket.get(field, 0)) + amount
                results.append(bucket[field])
            else:
                results.append(True)
        self._ops = []
        return results


class _FakeRedis:
    """In-memory stand-in for redis.Redis, covering exactly the
    operations SahmkRateLimiter uses (get/setex for the
    upstream-exhaustion flag, hincrby/hgetall/pipeline for the
    persisted day counters) -- enough to prove real cross-instance
    sharing (two SahmkRateLimiter objects given the *same* _FakeRedis*
    instance) without a real Redis server."""

    def __init__(self):
        self._kv: dict = {}
        self._hashes: dict = {}

    def get(self, key):
        return self._kv.get(key)

    def set(self, key, value, ex=None):
        self._kv[key] = value

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def pipeline(self):
        return _FakeRedisPipeline(self._hashes)


def test_rejects_non_positive_max_per_minute():
    with pytest.raises(ValueError):
        SahmkRateLimiter(max_per_minute=0)


def test_rejects_non_positive_max_per_day():
    with pytest.raises(ValueError):
        SahmkRateLimiter(max_per_minute=10, max_per_day=0)


@pytest.mark.asyncio
async def test_acquire_succeeds_under_the_limit():
    limiter = SahmkRateLimiter(max_per_minute=10)
    for _ in range(10):
        await limiter.acquire()  # must not sleep/raise -- still under the cap


@pytest.mark.asyncio
async def test_acquire_sleeps_once_the_per_minute_cap_is_reached(monkeypatch):
    """A no-op sleep mock would make this hang: the limiter's eviction
    check is real-time-based, so a sleep that doesn't actually advance
    time would spin forever recomputing the same non-expired window.
    The fake sleep here advances a fake clock instead, exactly like a
    real sleep would advance the real one."""
    fake_now = [1_000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        fake_now[0] += seconds

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    limiter = SahmkRateLimiter(max_per_minute=2)
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # 3rd call exceeds the 2/minute cap -- must wait

    assert len(sleep_calls) == 1
    assert 0 < sleep_calls[0] <= 60


@pytest.mark.asyncio
async def test_acquire_raises_once_daily_quota_is_spent():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=2)
    await limiter.acquire()
    await limiter.acquire()
    with pytest.raises(SahmkRateLimitExceededError):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_daily_quota_refusal_does_not_sleep(monkeypatch):
    """A spent daily quota must fail fast, never sleep toward
    tomorrow -- sleeping for up to 24h would make an ingestion job hang."""

    async def _fail_if_called(seconds):
        raise AssertionError(f"asyncio.sleep should never be called here (got {seconds})")

    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=1)
    await limiter.acquire()

    monkeypatch.setattr(asyncio, "sleep", _fail_if_called)
    with pytest.raises(SahmkRateLimitExceededError):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_no_daily_cap_by_default():
    limiter = SahmkRateLimiter(max_per_minute=1_000_000)
    for _ in range(50):
        await limiter.acquire()  # must never raise -- no max_per_day configured


def test_reset_clears_usage():
    limiter = SahmkRateLimiter(max_per_minute=1, max_per_day=1)
    limiter._minute_window.append(0.0)
    limiter._day_count = 1
    limiter._day_key = "2026-01-01"
    limiter.reset()
    assert list(limiter._minute_window) == []
    assert limiter._day_count == 0
    assert limiter._day_key is None


# --- priority-aware reservation for critical (live-market) callers ---------


def test_rejects_reserved_for_critical_without_max_per_day():
    with pytest.raises(ValueError):
        SahmkRateLimiter(max_per_minute=10, reserved_for_critical=5)


def test_rejects_negative_reserved_for_critical():
    with pytest.raises(ValueError):
        SahmkRateLimiter(max_per_minute=10, max_per_day=10, reserved_for_critical=-1)


def test_rejects_reserved_for_critical_exceeding_max_per_day():
    with pytest.raises(ValueError):
        SahmkRateLimiter(max_per_minute=10, max_per_day=10, reserved_for_critical=11)


@pytest.mark.asyncio
async def test_background_caller_refused_once_reserve_is_all_that_remains():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=5, reserved_for_critical=2)
    for _ in range(3):
        await limiter.acquire(priority=BACKGROUND)  # 5 - 2 = 3 background-eligible slots
    with pytest.raises(SahmkQuotaReservedForCriticalError):
        await limiter.acquire(priority=BACKGROUND)


@pytest.mark.asyncio
async def test_quota_reserved_error_is_a_rate_limit_exceeded_error():
    """Existing callers written against SahmkRateLimitExceededError
    (ingestion jobs' except blocks) must keep working unchanged."""
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=1, reserved_for_critical=1)
    with pytest.raises(SahmkRateLimitExceededError):
        await limiter.acquire(priority=BACKGROUND)


@pytest.mark.asyncio
async def test_critical_caller_can_spend_the_full_daily_quota_including_the_reserve():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=5, reserved_for_critical=2)
    for _ in range(3):
        await limiter.acquire(priority=BACKGROUND)
    for _ in range(2):
        await limiter.acquire(priority=CRITICAL)  # dips into the reserve -- must succeed
    with pytest.raises(SahmkRateLimitExceededError):
        await limiter.acquire(priority=CRITICAL)  # now the full daily cap is spent


@pytest.mark.asyncio
async def test_default_priority_is_critical_and_unaffected_by_reservation():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=2, reserved_for_critical=2)
    await limiter.acquire()  # no priority passed -- defaults to critical
    await limiter.acquire()
    with pytest.raises(SahmkRateLimitExceededError):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_zero_reserved_for_critical_disables_the_reservation():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=2, reserved_for_critical=0)
    await limiter.acquire(priority=BACKGROUND)
    await limiter.acquire(priority=BACKGROUND)  # would be refused if reservation were active
    with pytest.raises(SahmkRateLimitExceededError):
        await limiter.acquire(priority=BACKGROUND)


# --- get_status() ------------------------------------------------------------


def test_get_status_reflects_configuration_and_zero_usage():
    limiter = SahmkRateLimiter(max_per_minute=20, max_per_day=100, reserved_for_critical=10)
    status = limiter.get_status()
    assert status["max_per_minute"] == 20
    assert status["max_per_day"] == 100
    assert status["reserved_for_critical"] == 10
    assert status["requests_used_today"] == 0
    assert status["remaining_today"] == 100
    assert status["remaining_today_for_background"] == 90
    assert status["resets_at_utc"] is not None


@pytest.mark.asyncio
async def test_get_status_tracks_usage_by_priority():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=100, reserved_for_critical=10)
    await limiter.acquire(priority=CRITICAL)
    await limiter.acquire(priority=BACKGROUND)
    await limiter.acquire(priority=BACKGROUND)
    status = limiter.get_status()
    assert status["requests_used_today"] == 3
    assert status["critical_requests_used_today"] == 1
    assert status["background_requests_used_today"] == 2
    assert status["remaining_today"] == 97
    assert status["remaining_today_for_background"] == 87


def test_get_status_with_no_daily_cap_configured():
    limiter = SahmkRateLimiter(max_per_minute=20)
    status = limiter.get_status()
    assert status["max_per_day"] is None
    assert status["remaining_today"] is None
    assert status["remaining_today_for_background"] is None


# --- process-wide default singleton -----------------------------------------


def test_get_default_rate_limiter_returns_the_same_instance(monkeypatch):
    reset_default_rate_limiter()
    monkeypatch.setenv("SAHMK_MAX_REQUESTS_PER_MINUTE", "15")
    first = get_default_rate_limiter()
    second = get_default_rate_limiter()
    assert first is second
    assert first._max_per_minute == 15
    reset_default_rate_limiter()


def test_reset_default_rate_limiter_forces_a_fresh_instance(monkeypatch):
    reset_default_rate_limiter()
    monkeypatch.setenv("SAHMK_MAX_REQUESTS_PER_MINUTE", "5")
    first = get_default_rate_limiter()
    reset_default_rate_limiter()
    monkeypatch.setenv("SAHMK_MAX_REQUESTS_PER_MINUTE", "25")
    second = get_default_rate_limiter()
    assert first is not second
    assert second._max_per_minute == 25
    reset_default_rate_limiter()


def test_default_singleton_enforces_the_confirmed_real_daily_quota(monkeypatch):
    """2026-08-09 production evidence: SAHMK's real account quota is
    5000 requests/day. The singleton's default (no env override) must
    stay safely under that, with a real reserve carved out for
    live-market-critical work -- this is what actually fixes the root
    cause (the daily cap was previously None/unenforced by default)."""
    reset_default_rate_limiter()
    monkeypatch.delenv("SAHMK_MAX_REQUESTS_PER_DAY", raising=False)
    monkeypatch.delenv("SAHMK_RESERVED_FOR_CRITICAL_REQUESTS_PER_DAY", raising=False)
    limiter = get_default_rate_limiter()
    assert limiter._max_per_day == 4500
    assert limiter._max_per_day < 5000
    assert limiter._reserved_for_critical == 1000
    reset_default_rate_limiter()


# --- provider-truth reconciliation (2026-08-10 production evidence) --------
# Root cause fixed here: SahmkRateLimiter's own optimistic day_count
# reported a healthy budget while SAHMK's real account-wide quota was
# already exhausted for hours. record_upstream_daily_exhaustion() +
# acquire()'s pre-check are what make provider truth override this
# limiter's own estimate, with no assumed reset timezone anywhere.


@pytest.mark.asyncio
async def test_acquire_raises_immediately_after_upstream_exhaustion_recorded():
    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=4500, redis_client=None)
    limiter.record_upstream_daily_exhaustion(
        retry_after_seconds=54711,
        raw_message="Daily rate limit exceeded (5000 requests/day). Expected available in 54711 seconds.",
    )
    with pytest.raises(SahmkUpstreamQuotaExhaustedError) as excinfo:
        await limiter.acquire()
    assert excinfo.value.evidence is not None
    assert "Daily rate limit exceeded" in excinfo.value.evidence


@pytest.mark.asyncio
async def test_upstream_exhaustion_never_sleeps(monkeypatch):
    async def _fail_if_called(seconds):
        raise AssertionError(f"asyncio.sleep should never be called here (got {seconds})")

    limiter = SahmkRateLimiter(max_per_minute=100, redis_client=None)
    limiter.record_upstream_daily_exhaustion(retry_after_seconds=3600, raw_message="daily rate limit exceeded")

    monkeypatch.setattr(asyncio, "sleep", _fail_if_called)
    with pytest.raises(SahmkUpstreamQuotaExhaustedError):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_upstream_exhaustion_expires_after_its_own_evidence_based_reset_time():
    """No local day_count involved at all here -- proves the exhaustion
    flag itself is time-bounded by SAHMK's own reported figure, not a
    fixed/hard-coded schedule."""
    limiter = SahmkRateLimiter(max_per_minute=100, redis_client=None)
    limiter.record_upstream_daily_exhaustion(retry_after_seconds=3600, raw_message="daily rate limit exceeded")
    # Simulate the reset instant having already passed.
    limiter._local_upstream_reset_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await limiter.acquire()  # must not raise -- the recorded window has elapsed


def test_record_upstream_exhaustion_without_retry_after_uses_a_conservative_default_hold():
    limiter = SahmkRateLimiter(max_per_minute=100, redis_client=None)
    before = datetime.now(timezone.utc)
    limiter.record_upstream_daily_exhaustion(retry_after_seconds=None, raw_message="daily rate limit exceeded")
    assert limiter._local_upstream_reset_at is not None
    hold_seconds = (limiter._local_upstream_reset_at - before).total_seconds()
    assert 3000 < hold_seconds <= 3700  # ~1h default hold, not a guessed 24h


def test_get_status_reports_upstream_exhaustion_and_forces_remaining_to_zero():
    limiter = SahmkRateLimiter(max_per_minute=20, max_per_day=4500, reserved_for_critical=1000, redis_client=None)
    limiter.record_upstream_daily_exhaustion(
        retry_after_seconds=54711,
        raw_message="Daily rate limit exceeded (5000 requests/day). Expected available in 54711 seconds.",
    )
    status = limiter.get_status()
    assert status["upstream_confirmed_exhausted"] is True
    assert status["upstream_reset_at_utc"] is not None
    assert "Daily rate limit exceeded" in status["upstream_exhaustion_evidence"]
    # The core regression this fixes: never claim thousands of
    # requests remain once SAHMK's own evidence says otherwise.
    assert status["remaining_today"] == 0
    assert status["remaining_today_for_background"] == 0


def test_get_status_without_any_exhaustion_evidence_reports_false():
    limiter = SahmkRateLimiter(max_per_minute=20, max_per_day=4500, redis_client=None)
    status = limiter.get_status()
    assert status["upstream_confirmed_exhausted"] is False
    assert status["upstream_reset_at_utc"] is None
    assert status["upstream_exhaustion_evidence"] is None
    assert status["remaining_today"] == 4500


# --- Redis-backed cross-process/cross-worker sharing ------------------------


@pytest.mark.asyncio
async def test_upstream_exhaustion_is_shared_across_instances_via_redis():
    """The actual production scenario: one worker's real 429 must stop
    every other worker (a separate SahmkRateLimiter instance here,
    standing in for a separate process) from independently believing
    quota remains."""
    shared_redis = _FakeRedis()
    worker_a = SahmkRateLimiter(max_per_minute=100, max_per_day=4500, redis_client=shared_redis)
    worker_b = SahmkRateLimiter(max_per_minute=100, max_per_day=4500, redis_client=shared_redis)

    worker_a.record_upstream_daily_exhaustion(
        retry_after_seconds=3600, raw_message="Daily rate limit exceeded (5000 requests/day)."
    )

    with pytest.raises(SahmkUpstreamQuotaExhaustedError):
        await worker_b.acquire()


def test_quota_shared_across_workers_flag_reflects_redis_availability():
    with_redis = SahmkRateLimiter(max_per_minute=20, redis_client=_FakeRedis())
    assert with_redis.get_status()["quota_shared_across_workers"] is True


@pytest.mark.asyncio
async def test_day_counts_reconcile_from_redis_across_instances():
    """A fresh/restarted process (worker_b, zero local history) must
    pick up real usage another worker already made today instead of
    believing it has the full budget to itself."""
    shared_redis = _FakeRedis()
    worker_a = SahmkRateLimiter(max_per_minute=100, max_per_day=4500, redis_client=shared_redis)
    worker_b = SahmkRateLimiter(max_per_minute=100, max_per_day=4500, redis_client=shared_redis)

    for _ in range(3):
        await worker_a.acquire(priority=CRITICAL)
    await worker_a.acquire(priority=BACKGROUND)

    status_b = worker_b.get_status()
    assert status_b["requests_used_today"] >= 4
    assert status_b["critical_requests_used_today"] >= 3
    assert status_b["background_requests_used_today"] >= 1


@pytest.mark.asyncio
async def test_redis_failure_degrades_to_in_process_tracking_without_raising(monkeypatch):
    """Redis being unreachable (the common case in this test suite and
    in any environment without Redis configured) must never itself
    block or crash a legitimate SAHMK request."""

    class _BrokenRedis:
        def get(self, *_a, **_kw):
            raise ConnectionError("simulated Redis outage")

        def set(self, *_a, **_kw):
            raise ConnectionError("simulated Redis outage")

        def hgetall(self, *_a, **_kw):
            raise ConnectionError("simulated Redis outage")

        def pipeline(self):
            raise ConnectionError("simulated Redis outage")

    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=10, redis_client=_BrokenRedis())
    await limiter.acquire()  # must not raise despite every Redis call failing
    status = limiter.get_status()
    assert status["requests_used_today"] == 1
    assert status["quota_shared_across_workers"] is True  # a client is configured, even if unreachable


# --- per-operation accounting (SAHMK quota optimization mandate, 2026-08-16) -


@pytest.mark.asyncio
async def test_acquire_tracks_usage_by_operation():
    limiter = SahmkRateLimiter(max_per_minute=100, redis_client=None)
    await limiter.acquire(priority=CRITICAL, endpoint="quote", subsystem="stock_detail")
    await limiter.acquire(priority=BACKGROUND, endpoint="quote", subsystem="stock_detail")
    await limiter.acquire(priority=BACKGROUND, endpoint="ohlcv", subsystem="ingestion")

    by_operation = limiter.get_status()["by_operation"]
    assert by_operation["stock_detail:quote"] == 2
    assert by_operation["ingestion:ohlcv"] == 1


@pytest.mark.asyncio
async def test_acquire_without_endpoint_or_subsystem_falls_back_to_unclassified_other():
    limiter = SahmkRateLimiter(max_per_minute=100, redis_client=None)
    await limiter.acquire()  # no endpoint/subsystem -- still counted, never dropped
    assert limiter.get_status()["by_operation"] == {"unclassified:other": 1}


def test_reset_clears_operation_counts():
    limiter = SahmkRateLimiter(max_per_minute=1, redis_client=None)
    limiter._operation_counts = {"market_scan:quote": 5}
    limiter.reset()
    assert limiter.get_status()["by_operation"] == {}


@pytest.mark.asyncio
async def test_operation_counts_reconcile_from_redis_across_instances():
    """Same cross-process reconciliation guarantee day_count already
    has (see test_day_counts_reconcile_from_redis_across_instances),
    now proven for the per-operation breakdown too."""
    shared_redis = _FakeRedis()
    worker_a = SahmkRateLimiter(max_per_minute=100, redis_client=shared_redis)
    worker_b = SahmkRateLimiter(max_per_minute=100, redis_client=shared_redis)

    await worker_a.acquire(priority=BACKGROUND, endpoint="dividends", subsystem="ingestion")
    await worker_a.acquire(priority=BACKGROUND, endpoint="dividends", subsystem="ingestion")

    status_b = worker_b.get_status()
    assert status_b["by_operation"]["ingestion:dividends"] >= 2


def test_shared_redis_client_construction_failure_degrades_to_none(monkeypatch):
    """If settings.redis_dsn itself can't even build a client (missing/
    malformed config), the module-wide singleton must return None
    forever for this process rather than raise -- exercised via the
    default (no explicit redis_client=) singleton path."""
    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", _REAL_GET_SHARED_REDIS_CLIENT)
    monkeypatch.setattr(rate_limiter_module, "_shared_redis_client_attempted", False)
    monkeypatch.setattr(rate_limiter_module, "_shared_redis_client", None)

    def _raise(*_a, **_kw):
        raise RuntimeError("simulated: cannot construct a Redis client")

    monkeypatch.setattr(rate_limiter_module.redis_lib.Redis, "from_url", staticmethod(_raise))

    assert _REAL_GET_SHARED_REDIS_CLIENT() is None
    # Cached -- a second call doesn't attempt construction again.
    assert _REAL_GET_SHARED_REDIS_CLIENT() is None

    monkeypatch.setattr(rate_limiter_module, "_shared_redis_client_attempted", False)
