"""Tests against a real Redis instance -- skipped (not mocked) when
Redis isn't reachable, the same convention tests/unit/market_data/
sahmk/test_atomic_admission_lua_real_redis.py already establishes for
this codebase.

test_historical_ohlcv_lock.py's _FakeRedisWithEval.eval() only
*interprets* HistoricalOhlcvExecutionLock's _RELEASE_SCRIPT in Python;
it never actually exercises Redis's own real Lua engine. This file
closes that gap: every test here runs the real script against a real
redis.Redis client, so a syntax or logic regression in the script
itself (not merely in this codebase's idea of what it does) would be
caught here.
"""

import threading

import pytest


def is_redis_available() -> bool:
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not is_redis_available(), reason="Redis not available")

_TEST_LOCK_KEY = "basirah:test:historical_ohlcv:execution_lock:real_redis"


def _real_redis_client():
    import redis

    return redis.Redis(host="localhost", port=6379, decode_responses=True)


@pytest.fixture(autouse=True)
def _clean_test_key():
    client = _real_redis_client()
    client.delete(_TEST_LOCK_KEY)
    yield
    client.delete(_TEST_LOCK_KEY)


def _make_lock():
    from src.market_data.ingestion.historical_ohlcv_lock import HistoricalOhlcvExecutionLock

    return HistoricalOhlcvExecutionLock(redis_client=_real_redis_client(), lock_key=_TEST_LOCK_KEY)


def test_real_redis_acquire_is_atomic_set_nx():
    lock = _make_lock()
    assert lock.acquire(ttl_seconds=30) is True

    client = _real_redis_client()
    assert client.get(_TEST_LOCK_KEY) == lock.token
    ttl_ms = client.pttl(_TEST_LOCK_KEY)
    assert 0 < ttl_ms <= 30_000


def test_real_redis_second_acquire_fails_while_first_holds_it():
    first = _make_lock()
    second = _make_lock()
    assert first.acquire(ttl_seconds=30) is True
    assert second.acquire(ttl_seconds=30) is False


def test_real_redis_release_runs_the_actual_lua_script_and_deletes_owned_key():
    lock = _make_lock()
    lock.acquire(ttl_seconds=30)

    lock.release()

    client = _real_redis_client()
    assert client.get(_TEST_LOCK_KEY) is None


def test_real_redis_release_lua_script_is_ownership_safe():
    """The real Lua script itself, not a Python-side approximation of
    it, must refuse to delete a key whose current value no longer
    matches this instance's own token."""
    original = _make_lock()
    original.acquire(ttl_seconds=30)

    client = _real_redis_client()
    client.delete(_TEST_LOCK_KEY)  # simulate expiry
    new_holder = _make_lock()
    assert new_holder.acquire(ttl_seconds=30) is True

    original.release()  # must NOT delete new_holder's real key

    assert client.get(_TEST_LOCK_KEY) == new_holder.token


def test_real_redis_ttl_expiry_lets_a_new_holder_acquire_after_real_wall_clock_time():
    """Phase 6 TTL-safety scenario: simulates a crashed holder (never
    calls release()) using a genuinely short TTL and a real wait --
    not a simulated expire_now() helper -- proving the real PX option
    actually bounds how long a crashed process can block every future
    historical_ohlcv attempt."""
    import time

    crashed_holder = _make_lock()
    assert crashed_holder.acquire(ttl_seconds=0.2) is True

    still_blocked = _make_lock()
    assert still_blocked.acquire(ttl_seconds=30) is False  # still within the TTL window

    time.sleep(0.35)  # real wall-clock wait past the 0.2s TTL

    new_holder = _make_lock()
    assert new_holder.acquire(ttl_seconds=30) is True


def test_real_redis_concurrent_threads_only_one_wins():
    """N real OS threads, each with its own real redis.Redis
    connection, racing SET NX PX against the same real server --
    the strongest available proof the atomic primitive itself (not
    this codebase's use of it) is genuinely exclusive under real
    concurrency."""
    n = 16
    results = [None] * n
    barrier = threading.Barrier(n)

    def _attempt(i):
        lock = _make_lock()
        barrier.wait()
        results[i] = lock.acquire(ttl_seconds=30)

    threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r is True) == 1
