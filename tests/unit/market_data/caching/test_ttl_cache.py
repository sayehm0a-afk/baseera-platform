"""Unit tests for TTLCache."""

import asyncio

import pytest

from src.market_data.caching.ttl_cache import TTLCache


@pytest.mark.asyncio
async def test_get_or_compute_calls_compute_once_on_miss():
    cache = TTLCache(default_ttl_seconds=60.0)
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return "value"

    result = await cache.get_or_compute("k", compute)
    assert result == "value"
    assert calls == 1


@pytest.mark.asyncio
async def test_get_or_compute_returns_cached_value_without_recomputing():
    cache = TTLCache(default_ttl_seconds=60.0)
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return calls

    first = await cache.get_or_compute("k", compute)
    second = await cache.get_or_compute("k", compute)
    assert first == second == 1


@pytest.mark.asyncio
async def test_get_or_compute_recomputes_after_ttl_expiry():
    cache = TTLCache(default_ttl_seconds=0.01)
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return calls

    first = await cache.get_or_compute("k", compute)
    await asyncio.sleep(0.02)
    second = await cache.get_or_compute("k", compute)
    assert first == 1
    assert second == 2


@pytest.mark.asyncio
async def test_get_or_compute_coalesces_concurrent_calls_for_same_key():
    cache = TTLCache(default_ttl_seconds=60.0)
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return "shared"

    results = await asyncio.gather(
        cache.get_or_compute("k", compute),
        cache.get_or_compute("k", compute),
        cache.get_or_compute("k", compute),
    )
    assert results == ["shared", "shared", "shared"]
    assert calls == 1


@pytest.mark.asyncio
async def test_get_or_compute_does_not_cache_on_failure():
    cache = TTLCache(default_ttl_seconds=60.0)
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await cache.get_or_compute("k", compute)

    assert cache.get("k") is cache.get("does-not-exist")  # both MISSING sentinel
    with pytest.raises(RuntimeError):
        await cache.get_or_compute("k", compute)
    assert calls == 2


@pytest.mark.asyncio
async def test_concurrent_callers_all_see_failure_when_compute_raises():
    cache = TTLCache(default_ttl_seconds=60.0)

    async def compute():
        await asyncio.sleep(0.01)
        raise ValueError("nope")

    results = await asyncio.gather(
        cache.get_or_compute("k", compute),
        cache.get_or_compute("k", compute),
        return_exceptions=True,
    )
    assert all(isinstance(r, ValueError) for r in results)


def test_set_and_get_roundtrip():
    cache = TTLCache()
    cache.set("k", 42)
    assert cache.get("k") == 42


def test_clear_removes_all_entries():
    cache = TTLCache()
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("a") is _MISSING
    assert cache.get("b") is _MISSING


def test_cached_none_is_distinguishable_from_missing():
    cache = TTLCache()
    cache.set("k", None)
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("k") is None
    assert cache.get("other-key") is _MISSING
