"""Tests for src.market_data.caching.redis_shared_cache -- the
Redis-backed cross-Gunicorn-worker cache for expensive SAHMK provider
responses. Uses a hand-rolled in-memory fake (same pattern as
tests/unit/market_data/sahmk/test_rate_limiter.py's `_FakeRedis`), not
a real Redis server, so these never touch the network and stay fast
and hermetic.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from src.market_data.caching import redis_shared_cache as cache_module
from src.market_data.caching.redis_shared_cache import (
    CacheBackendHealth,
    SharedCacheStats,
    SharedTTLCache,
    get_observability_snapshot,
)


class _FakeRedis:
    """Covers exactly the operations SharedTTLCache uses: get/setex for
    the cached value, set(nx=True, px=...) + delete for the stampede
    lock, ping for health. `raise_on` lets a test simulate a Redis
    outage on a specific operation without a real connection failure."""

    def __init__(self, raise_on: Optional[set] = None):
        self._kv: dict = {}
        self._raise_on = raise_on or set()

    def _maybe_raise(self, op: str):
        if op in self._raise_on:
            raise ConnectionError(f"simulated Redis outage on {op}")

    def get(self, key):
        self._maybe_raise("get")
        return self._kv.get(key)

    def set(self, key, value, nx=False, px=None, ex=None):
        self._maybe_raise("set")
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def setex(self, key, seconds, value):
        self._maybe_raise("setex")
        self._kv[key] = value

    def delete(self, key):
        self._maybe_raise("delete")
        self._kv.pop(key, None)

    def ping(self):
        self._maybe_raise("ping")
        return True


@dataclass(frozen=True)
class _Sample:
    symbol: str
    price: float
    timestamp: datetime
    change: Optional[float] = None


@pytest.fixture(autouse=True)
def _isolate_shared_singleton():
    """The module-level lazy Redis singleton must never leak between
    tests -- every test here passes its own fake explicitly via
    `redis_client=`, but resetting the singleton too keeps this file
    safe even if a future test forgets to."""
    cache_module.reset_shared_redis_client()
    yield
    cache_module.reset_shared_redis_client()


# --- basic hit/miss/hermetic behavior ---------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_computes_then_hit_reuses_without_recomputing():
    fake = _FakeRedis()
    cache = SharedTTLCache("test", redis_client=fake)
    calls = []

    async def _compute():
        calls.append(1)
        return {"value": 42}

    first = await cache.get_or_compute("k1", _compute, ttl_seconds=60)
    second = await cache.get_or_compute("k1", _compute, ttl_seconds=60)

    assert first == {"value": 42}
    assert second == {"value": 42}
    assert len(calls) == 1
    assert cache.stats.misses == 1
    assert cache.stats.hits == 1
    assert cache.stats.provider_calls == 1


@pytest.mark.asyncio
async def test_different_keys_never_collide():
    fake = _FakeRedis()
    cache = SharedTTLCache("test", redis_client=fake)

    async def _compute_a():
        return "A"

    async def _compute_b():
        return "B"

    result_a = await cache.get_or_compute(("quote", "2222"), _compute_a, ttl_seconds=60)
    result_b = await cache.get_or_compute(("quote", "1120"), _compute_b, ttl_seconds=60)

    assert result_a == "A"
    assert result_b == "B"


# --- cross-worker sharing -----------------------------------------------------


@pytest.mark.asyncio
async def test_result_computed_by_one_cache_instance_is_reused_by_another():
    """The core cross-Gunicorn-worker guarantee: two independent
    SharedTTLCache instances (standing in for two separate worker
    processes) sharing the same Redis must reuse one computed result."""
    fake = _FakeRedis()
    worker_1_cache = SharedTTLCache("test", redis_client=fake)
    worker_2_cache = SharedTTLCache("test", redis_client=fake)
    calls = []

    async def _compute():
        calls.append(1)
        return {"symbol": "2222", "price": 30.5}

    result_1 = await worker_1_cache.get_or_compute("shared-key", _compute, ttl_seconds=60)
    result_2 = await worker_2_cache.get_or_compute("shared-key", _compute, ttl_seconds=60)

    assert result_1 == result_2
    assert len(calls) == 1  # the second worker never called SAHMK itself
    assert worker_2_cache.stats.hits == 1
    assert worker_2_cache.stats.misses == 0


# --- stampede prevention ------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_requests_for_the_same_key_coalesce_into_one_provider_call():
    fake = _FakeRedis()
    cache_a = SharedTTLCache("test", redis_client=fake)
    cache_b = SharedTTLCache("test", redis_client=fake)
    calls = []

    async def _compute():
        calls.append(1)
        await asyncio.sleep(0.05)  # simulate a real SAHMK round trip
        return {"value": 42}

    results = await asyncio.gather(
        cache_a.get_or_compute("stampede-key", _compute, ttl_seconds=60),
        cache_b.get_or_compute("stampede-key", _compute, ttl_seconds=60),
    )

    assert results[0] == results[1] == {"value": 42}
    assert len(calls) == 1, "both concurrent callers must never trigger two separate SAHMK calls"
    assert cache_a.stats.provider_calls + cache_b.stats.provider_calls == 1
    assert cache_a.stats.coalesced_waits + cache_b.stats.coalesced_waits == 1


@pytest.mark.asyncio
async def test_stuck_lock_from_a_crashed_winner_falls_through_to_direct_compute(monkeypatch):
    """If the lock-holding worker dies before writing a result, a
    poller must not deadlock -- once its poll budget is exhausted it
    computes the value itself."""
    monkeypatch.setattr(cache_module, "_POLL_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(cache_module, "_POLL_INTERVAL_SECONDS", 0.01)

    fake = _FakeRedis()
    cache = SharedTTLCache("test", redis_client=fake)
    # Simulate another worker having won the lock and then crashed --
    # the lock key exists, the value key never gets written.
    fake._kv[cache._redis_key("stuck-key") + ":lock"] = "1"

    async def _compute():
        return "recovered"

    result = await cache.get_or_compute("stuck-key", _compute, ttl_seconds=60)

    assert result == "recovered"


# --- safe degradation on Redis failure ----------------------------------------


@pytest.mark.asyncio
async def test_redis_get_failure_degrades_to_local_cache_without_raising():
    fake = _FakeRedis(raise_on={"get"})
    cache = SharedTTLCache("test", redis_client=fake)

    async def _compute():
        return "ok"

    result = await cache.get_or_compute("k", _compute, ttl_seconds=60)

    assert result == "ok"
    assert cache.stats.redis_errors >= 1


@pytest.mark.asyncio
async def test_no_redis_client_at_all_degrades_to_local_ttl_cache(monkeypatch):
    # Forces _get_shared_redis_client() to fail deterministically,
    # regardless of whether a real Redis happens to be reachable from
    # wherever this test suite runs (matches
    # test_backend_health_disabled_when_no_redis_client's own pattern) --
    # otherwise this test would silently exercise the real-Redis path
    # instead of the local-fallback path it claims to cover.
    def _raise(*args, **kwargs):
        raise ConnectionError("simulated: no Redis reachable")

    monkeypatch.setattr(cache_module.redis_lib.Redis, "from_url", staticmethod(_raise))

    cache = SharedTTLCache("test", redis_client=None)
    calls = []

    async def _compute():
        calls.append(1)
        return "local-only"

    first = await cache.get_or_compute("k", _compute, ttl_seconds=60)
    second = await cache.get_or_compute("k", _compute, ttl_seconds=60)

    assert first == second == "local-only"
    assert len(calls) == 1  # the local TTLCache fallback still avoids a duplicate compute


@pytest.mark.asyncio
async def test_setex_failure_still_returns_the_freshly_computed_value():
    fake = _FakeRedis(raise_on={"setex"})
    cache = SharedTTLCache("test", redis_client=fake)

    async def _compute():
        return "fresh"

    result = await cache.get_or_compute("k", _compute, ttl_seconds=60)

    assert result == "fresh"
    assert cache.stats.redis_errors >= 1


# --- backend health -----------------------------------------------------------


def test_backend_health_disabled_when_no_redis_client(monkeypatch):
    # Forces _get_shared_redis_client() to fail deterministically,
    # regardless of whether a real Redis happens to be reachable from
    # wherever this test suite runs (matches test_rate_limiter.py's
    # own pattern for the same "no Redis configured" scenario).
    def _raise(*args, **kwargs):
        raise ConnectionError("simulated: no Redis reachable")

    monkeypatch.setattr(cache_module.redis_lib.Redis, "from_url", staticmethod(_raise))

    cache = SharedTTLCache("test", redis_client=None)
    assert cache.backend_health == CacheBackendHealth.DISABLED


def test_backend_health_healthy_when_ping_succeeds():
    cache = SharedTTLCache("test", redis_client=_FakeRedis())
    assert cache.backend_health == CacheBackendHealth.HEALTHY


def test_backend_health_degraded_when_ping_fails():
    cache = SharedTTLCache("test", redis_client=_FakeRedis(raise_on={"ping"}))
    assert cache.backend_health == CacheBackendHealth.DEGRADED


def test_observability_snapshot_never_exposes_redis_credentials():
    fake = _FakeRedis()
    caches = {"quote": SharedTTLCache("quote", redis_client=fake)}
    snapshot = get_observability_snapshot(caches)

    assert snapshot["backend_health"] == CacheBackendHealth.HEALTHY
    assert snapshot["by_namespace"]["quote"] == {
        "hits": 0, "misses": 0, "coalesced_waits": 0, "provider_calls": 0, "redis_errors": 0,
    }
    dumped = str(snapshot)
    assert "redis://" not in dumped
    assert "password" not in dumped.lower()


# --- per-operation accounting (SAHMK quota optimization mandate, 2026-08-16) -


@pytest.mark.asyncio
async def test_by_operation_breakdown_derives_endpoint_from_the_cache_key():
    fake = _FakeRedis()
    cache = SharedTTLCache("sahmk_market_data", redis_client=fake)

    async def _compute():
        return {"value": 1}

    await cache.get_or_compute(("quote", "2222"), _compute, ttl_seconds=60)
    await cache.get_or_compute(("quote", "2222"), _compute, ttl_seconds=60)  # hit
    await cache.get_or_compute(("dividends", "1120"), _compute, ttl_seconds=60)

    assert cache.stats_by_operation["unclassified:quote"].misses == 1
    assert cache.stats_by_operation["unclassified:quote"].hits == 1
    assert cache.stats_by_operation["unclassified:quote"].provider_calls == 1
    assert cache.stats_by_operation["unclassified:dividends"].misses == 1


@pytest.mark.asyncio
async def test_by_operation_breakdown_includes_the_active_operation_scope_subsystem():
    from src.market_data.sahmk.operation_scope import MARKET_SCAN, operation_scope

    fake = _FakeRedis()
    cache = SharedTTLCache("sahmk_market_data", redis_client=fake)

    async def _compute():
        return {"value": 1}

    with operation_scope(MARKET_SCAN):
        await cache.get_or_compute(("quote", "2222"), _compute, ttl_seconds=60)

    assert cache.stats_by_operation["market_scan:quote"].misses == 1
    # Flat totals stay unaffected -- this is an additive breakdown, not a
    # replacement for the existing aggregate counters.
    assert cache.stats.misses == 1


@pytest.mark.asyncio
async def test_coalesced_wait_counts_as_a_hit_and_a_duplicate_request_prevented_per_operation():
    fake = _FakeRedis()
    cache_a = SharedTTLCache("sahmk_market_data", redis_client=fake)
    cache_b = SharedTTLCache("sahmk_market_data", redis_client=fake)

    async def _slow_compute():
        await asyncio.sleep(0.05)
        return {"value": 1}

    results = await asyncio.gather(
        cache_a.get_or_compute(("quote", "2222"), _slow_compute, ttl_seconds=60),
        cache_b.get_or_compute(("quote", "2222"), _slow_compute, ttl_seconds=60),
    )
    assert results[0] == results[1] == {"value": 1}

    total_provider_calls = (
        cache_a.stats_by_operation["unclassified:quote"].provider_calls
        + cache_b.stats_by_operation["unclassified:quote"].provider_calls
    )
    total_coalesced = (
        cache_a.stats_by_operation.get("unclassified:quote", SharedCacheStats()).coalesced_waits
        + cache_b.stats_by_operation.get("unclassified:quote", SharedCacheStats()).coalesced_waits
    )
    assert total_provider_calls == 1
    assert total_coalesced == 1


def test_get_observability_snapshot_includes_by_operation():
    fake = _FakeRedis()
    cache = SharedTTLCache("sahmk_market_data", redis_client=fake)
    cache.stats_by_operation["market_scan:quote"] = SharedCacheStats(hits=3, misses=1)

    snapshot = get_observability_snapshot({"sahmk_market_data": cache})

    assert snapshot["by_operation"]["market_scan:quote"] == {
        "hits": 3, "misses": 1, "coalesced_waits": 0, "provider_calls": 0, "redis_errors": 0,
    }


# --- dataclass encode/decode round-trip ---------------------------------------


@pytest.mark.asyncio
async def test_dataclass_with_datetime_field_round_trips_through_redis():
    fake = _FakeRedis()
    cache = SharedTTLCache("test", redis_client=fake)
    original = _Sample(symbol="2222", price=30.5, timestamp=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc), change=0.5)

    async def _compute():
        return original

    await cache.get_or_compute("dc-key", _compute, ttl_seconds=60, model=_Sample)
    # Second call hits Redis (not the local fallback), proving the
    # value survived a real JSON encode/decode round trip.
    result = await cache.get_or_compute("dc-key", _compute, ttl_seconds=60, model=_Sample)

    assert result == original
    assert isinstance(result.timestamp, datetime)
    assert cache.stats.hits == 1


@pytest.mark.asyncio
async def test_list_of_dataclasses_round_trips_through_redis():
    fake = _FakeRedis()
    cache = SharedTTLCache("test", redis_client=fake)
    original = [
        _Sample(symbol="2222", price=30.5, timestamp=datetime(2026, 8, 11, tzinfo=timezone.utc)),
        _Sample(symbol="1120", price=45.0, timestamp=datetime(2026, 8, 10, tzinfo=timezone.utc), change=-1.2),
    ]

    async def _compute():
        return original

    await cache.get_or_compute("list-key", _compute, ttl_seconds=60, model=_Sample)
    result = await cache.get_or_compute("list-key", _compute, ttl_seconds=60, model=_Sample)

    assert result == original
    assert all(isinstance(item.timestamp, datetime) for item in result)


@pytest.mark.asyncio
async def test_non_dataclass_value_round_trips_without_a_model():
    fake = _FakeRedis()
    cache = SharedTTLCache("test", redis_client=fake)

    async def _compute():
        return {"raw": True, "count": 3}

    await cache.get_or_compute("plain-key", _compute, ttl_seconds=60)
    result = await cache.get_or_compute("plain-key", _compute, ttl_seconds=60)

    assert result == {"raw": True, "count": 3}
