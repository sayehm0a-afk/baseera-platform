"""Tests against a real Redis instance -- skipped (not mocked) when
Redis isn't reachable, the same convention
tests/integration/test_production_integration.py and
tests/unit/auth/test_token_store.py already establish for this
codebase's other Redis-touching code.

Second independent PR #99 audit finding (P2, non-blocking): every
existing test in test_rate_limiter.py that constructs a SahmkRateLimiter
with `max_per_day` set uses either `redis_client=None` (routed through
that file's own autouse fixture, which disables the shared singleton)
or a hand-written `_FakeRedis`/`_BrokenRedis` stand-in -- neither of
which implements `eval()`. A `max_per_day`-gated acquire() against any
of those therefore always raises AttributeError from
`client.eval(...)`, which `_atomic_admit_and_increment` catches and
silently degrades to the pre-existing local-only fallback. This means
no committed, CI-run test actually executes `_ATOMIC_ADMIT_LUA_SCRIPT`
itself -- a syntax or logic regression in that script could ship with
a fully green test suite.

This file closes that gap: every test here uses a REAL redis.Redis
client with a genuinely working `eval()`, so `_atomic_admit_and_increment`
takes its atomic branch, not the fallback. Nothing here mocks or
duplicates the Lua script -- it is exercised exactly as production
runs it.
"""

import multiprocessing as mp
import sys

import pytest


def is_redis_available() -> bool:
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not is_redis_available(), reason="Redis not available")

_REPO_ROOT = "/home/user/baseera-platform"


def _real_redis_client():
    import redis

    return redis.Redis(host="localhost", port=6379, decode_responses=True)


def _make_limiter(max_per_day=100, reserved_for_critical=30, reserved_for_live_scan=20, max_per_minute=1_000_000):
    from src.market_data.sahmk.rate_limiter import SahmkRateLimiter

    return SahmkRateLimiter(
        max_per_minute=max_per_minute,
        max_per_day=max_per_day,
        reserved_for_critical=reserved_for_critical,
        reserved_for_live_scan=reserved_for_live_scan,
        redis_client=_real_redis_client(),
    )


@pytest.fixture(autouse=True)
def _clean_up_quota_keys():
    client = _real_redis_client()
    for key in client.keys("sahmk:quota:day:*"):
        client.delete(key)
    yield
    for key in client.keys("sahmk:quota:day:*"):
        client.delete(key)


# --- direct _atomic_admit_and_increment tests -------------------------------
# Calls the exact method acquire() calls, against the exact shipped
# _ATOMIC_ADMIT_LUA_SCRIPT, with a real Redis client -- the most direct
# possible proof of the script's own boundary behavior, deterministic
# and fast (no asyncio, no per-minute-window wait involved).


def test_atomic_path_is_actually_taken_not_fallback():
    """Phase 3's mandatory proof: the real Lua path returns a definite
    (admitted, reason) tuple, never None, against a real Redis client.
    None is exactly what a silent fallback would look like."""
    from src.market_data.sahmk.request_priority import CRITICAL

    limiter = _make_limiter()
    result = limiter._atomic_admit_and_increment(CRITICAL, "unclassified:other", limiter._day_key or "test-day")
    assert result is not None, "atomic admission returned None -- this proves it silently fell back, not the real Lua path"
    admitted, reason = result
    assert admitted is True
    assert reason == "admitted"


def test_daily_cap_100_proven_by_direct_lua_calls():
    """Phase 2.A: exactly 100 admissible requests succeed, request 101
    is rejected -- with reserves at 0 so only the absolute cap is in
    play."""
    from src.market_data.sahmk.request_priority import CRITICAL

    limiter = _make_limiter(max_per_day=100, reserved_for_critical=0, reserved_for_live_scan=0)
    day_key = limiter._day_key or "test-day"
    admitted_count = 0
    for _ in range(100):
        result = limiter._atomic_admit_and_increment(CRITICAL, "unclassified:other", day_key)
        assert result is not None
        admitted, reason = result
        assert admitted is True, f"expected admission but got refusal: {reason}"
        admitted_count += 1
    assert admitted_count == 100

    result = limiter._atomic_admit_and_increment(CRITICAL, "unclassified:other", day_key)
    admitted, reason = result
    assert admitted is False
    assert reason == "daily_cap"


def test_background_cap_50_proven_by_direct_lua_calls():
    """Phase 2.B: with max_per_day=100, critical reserve=30, live_scan
    reserve=20 -- BACKGROUND may admit no more than 50; the 51st is
    rejected."""
    from src.market_data.sahmk.request_priority import BACKGROUND

    limiter = _make_limiter(max_per_day=100, reserved_for_critical=30, reserved_for_live_scan=20)
    day_key = limiter._day_key or "test-day"
    for i in range(50):
        result = limiter._atomic_admit_and_increment(BACKGROUND, "unclassified:other", day_key)
        admitted, reason = result
        assert admitted is True, f"background request {i + 1}/50 unexpectedly refused: {reason}"

    result = limiter._atomic_admit_and_increment(BACKGROUND, "unclassified:other", day_key)
    admitted, reason = result
    assert admitted is False
    assert reason == "live_scan_reserve"


def test_background_plus_live_scan_cap_70_proven_and_live_scan_cannot_touch_critical():
    """Phase 2.C: background+live_scan may admit up to 70 total; the
    next LIVE_SCAN request past that boundary is refused (it would be
    consuming the CRITICAL reserve)."""
    from src.market_data.sahmk.request_priority import BACKGROUND, LIVE_SCAN

    limiter = _make_limiter(max_per_day=100, reserved_for_critical=30, reserved_for_live_scan=20)
    day_key = limiter._day_key or "test-day"
    admitted_count = 0
    for _ in range(50):
        admitted, _ = limiter._atomic_admit_and_increment(BACKGROUND, "unclassified:other", day_key)
        assert admitted is True
        admitted_count += 1
    for _ in range(20):
        admitted, reason = limiter._atomic_admit_and_increment(LIVE_SCAN, "unclassified:other", day_key)
        assert admitted is True, f"live_scan request unexpectedly refused: {reason}"
        admitted_count += 1
    assert admitted_count == 70

    admitted, reason = limiter._atomic_admit_and_increment(LIVE_SCAN, "unclassified:other", day_key)
    assert admitted is False
    assert reason == "critical_reserve"


def test_critical_access_up_to_the_global_cap_proven():
    """Phase 2.D: CRITICAL requests may use the reserved critical
    segment, all the way up to the global 100 cap, even after
    background+live_scan have exhausted the first 70."""
    from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL, LIVE_SCAN

    limiter = _make_limiter(max_per_day=100, reserved_for_critical=30, reserved_for_live_scan=20)
    day_key = limiter._day_key or "test-day"
    for _ in range(50):
        assert limiter._atomic_admit_and_increment(BACKGROUND, "unclassified:other", day_key)[0] is True
    for _ in range(20):
        assert limiter._atomic_admit_and_increment(LIVE_SCAN, "unclassified:other", day_key)[0] is True

    for i in range(30):
        admitted, reason = limiter._atomic_admit_and_increment(CRITICAL, "unclassified:other", day_key)
        assert admitted is True, f"critical request {i + 1}/30 unexpectedly refused: {reason}"

    admitted, reason = limiter._atomic_admit_and_increment(CRITICAL, "unclassified:other", day_key)
    assert admitted is False
    assert reason == "daily_cap"


# --- full acquire() integration, proving no silent fallback ----------------


@pytest.mark.asyncio
async def test_acquire_uses_the_real_atomic_path_for_every_call_not_fallback(monkeypatch):
    """Wraps (does not replace) _atomic_admit_and_increment to record
    whether every acquire() call during this test actually took the
    real-Redis atomic branch -- proving the public API, not just the
    private method in isolation, reaches the real Lua script."""
    from src.market_data.sahmk.rate_limiter import SahmkRateLimiter
    from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL

    limiter = _make_limiter(max_per_day=10, reserved_for_critical=3, reserved_for_live_scan=2)
    real_method = SahmkRateLimiter._atomic_admit_and_increment
    calls = []

    def _spy(self, priority, operation_key, day_key):
        result = real_method(self, priority, operation_key, day_key)
        calls.append(result)
        return result

    monkeypatch.setattr(SahmkRateLimiter, "_atomic_admit_and_increment", _spy)

    for _ in range(5):
        await limiter.acquire(priority=BACKGROUND)
    await limiter.acquire(priority=CRITICAL)

    assert len(calls) == 6
    assert all(c is not None for c in calls), "at least one acquire() call silently fell back instead of using the real Lua path"


@pytest.mark.asyncio
async def test_redis_state_reflects_exactly_what_acquire_admitted():
    """Cross-checks the real Redis hash directly against acquire()'s
    own admitted count -- proving the atomic increment genuinely wrote
    to Redis, not merely returned a locally-computed answer."""
    from src.market_data.sahmk.request_priority import BACKGROUND

    limiter = _make_limiter(max_per_day=10, reserved_for_critical=0, reserved_for_live_scan=0)
    for _ in range(7):
        await limiter.acquire(priority=BACKGROUND)
    day_key = limiter._day_key  # only set once acquire() has run _roll_day_window_locked()

    client = _real_redis_client()
    raw = client.hgetall(limiter._redis_day_hash_key(day_key))
    assert int(raw["total"]) == 7
    assert int(raw["background"]) == 7


# --- concurrency: multiple real OS processes against the same real Redis ---


def _race_worker(priority, n_attempts, result_queue, barrier):
    import asyncio

    sys.path.insert(0, _REPO_ROOT)
    import redis as redis_lib

    from src.market_data.sahmk.rate_limiter import SahmkRateLimiter, SahmkRateLimitExceededError

    barrier.wait()

    async def run():
        limiter = SahmkRateLimiter(
            max_per_minute=1_000_000, max_per_day=100, reserved_for_critical=30, reserved_for_live_scan=20,
            redis_client=redis_lib.Redis(host="localhost", port=6379, decode_responses=True),
        )
        admitted = 0
        for _ in range(40):
            try:
                await limiter.acquire(priority=priority)
                admitted += 1
            except SahmkRateLimitExceededError:
                pass
        return admitted

    result_queue.put((priority, asyncio.run(run())))


def _run_race_trial(n_workers):
    from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL, LIVE_SCAN

    client = _real_redis_client()
    for key in client.keys("sahmk:quota:day:*"):
        client.delete(key)

    priorities = ([BACKGROUND, LIVE_SCAN, CRITICAL] * ((n_workers // 3) + 1))[:n_workers]
    result_queue = mp.Queue()
    barrier = mp.Barrier(n_workers)
    processes = [mp.Process(target=_race_worker, args=(p, 40, result_queue, barrier)) for p in priorities]
    for proc in processes:
        proc.start()
    for proc in processes:
        proc.join()

    admitted = {BACKGROUND: 0, LIVE_SCAN: 0, CRITICAL: 0}
    while not result_queue.empty():
        p, count = result_queue.get()
        admitted[p] += count

    for key in client.keys("sahmk:quota:day:*"):
        client.delete(key)
    return admitted


@pytest.mark.parametrize("n_workers", [2, 4, 8, 16])
def test_no_overspend_under_real_concurrent_multi_process_load(n_workers):
    """Phase 5's mandatory concurrency regression: real OS processes,
    barrier-synchronized to start simultaneously, racing the same real
    Redis keys. No +1 overspend is acceptable -- this is exactly the
    scenario the original P1 finding reproduced (before the atomic Lua
    fix) and this test now guards against a regression of it."""
    for _ in range(3):
        admitted = _run_race_trial(n_workers)
        total = sum(admitted.values())
        assert total <= 100, f"workers={n_workers}: total admissions {total} exceeded the daily cap of 100: {admitted}"
        assert admitted["background"] <= 50, f"workers={n_workers}: background reserve leaked: {admitted}"
        assert admitted["background"] + admitted["live_scan"] <= 70, (
            f"workers={n_workers}: background+live_scan leaked into the critical reserve: {admitted}"
        )


# --- failure/fallback separation --------------------------------------------


@pytest.mark.asyncio
async def test_redis_connection_failure_falls_back_and_never_uses_the_real_lua_path(monkeypatch):
    """The pre-existing fallback design must remain intact and
    separate from the real-Lua path this file otherwise exercises --
    a genuinely broken Redis connection must degrade to local-only
    tracking, not raise, and must NOT be confused with the atomic path."""
    import redis as redis_lib

    from src.market_data.sahmk.rate_limiter import SahmkRateLimiter
    from src.market_data.sahmk.request_priority import CRITICAL

    class _UnreachableRedis:
        def eval(self, *_a, **_kw):
            raise redis_lib.exceptions.ConnectionError("simulated real Redis outage")

        def hgetall(self, *_a, **_kw):
            raise redis_lib.exceptions.ConnectionError("simulated real Redis outage")

        def get(self, *_a, **_kw):
            raise redis_lib.exceptions.ConnectionError("simulated real Redis outage")

        def pipeline(self):
            raise redis_lib.exceptions.ConnectionError("simulated real Redis outage")

    limiter = SahmkRateLimiter(max_per_minute=100, max_per_day=10, redis_client=_UnreachableRedis())
    await limiter.acquire(priority=CRITICAL)  # must not raise
    status = limiter.get_status()
    assert status["requests_used_today"] == 1
