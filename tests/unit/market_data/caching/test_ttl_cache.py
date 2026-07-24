"""Unit tests for the in-memory TTLCache."""

import pytest

from src.market_data.caching.ttl_cache import TTLCache


def test_get_missing_key_returns_missing_sentinel_not_none():
    cache = TTLCache()
    assert cache.get("absent") is not None
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("absent") is _MISSING


def test_set_then_get_returns_stored_value():
    cache = TTLCache()
    cache.set("k", {"a": 1})
    assert cache.get("k") == {"a": 1}


def test_cached_none_is_distinguishable_from_missing():
    cache = TTLCache()
    cache.set("k", None)
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("k") is None
    assert cache.get("k") is not _MISSING


def test_entry_expires_after_ttl(monkeypatch):
    cache = TTLCache()
    fake_time = [1000.0]
    monkeypatch.setattr("time.time", lambda: fake_time[0])

    cache.set("k", "v", ttl_seconds=5)
    assert cache.get("k") == "v"

    fake_time[0] += 5.1
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("k") is _MISSING


def test_clear_removes_all_entries():
    cache = TTLCache()
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("a") is _MISSING
    assert cache.get("b") is _MISSING


@pytest.mark.asyncio
async def test_get_or_compute_calls_compute_only_on_miss():
    cache = TTLCache()
    call_count = 0

    async def compute():
        nonlocal call_count
        call_count += 1
        return "computed"

    first = await cache.get_or_compute("k", compute)
    second = await cache.get_or_compute("k", compute)

    assert first == "computed"
    assert second == "computed"
    assert call_count == 1


@pytest.mark.asyncio
async def test_get_or_compute_recomputes_after_expiry(monkeypatch):
    cache = TTLCache(default_ttl_seconds=1)
    fake_time = [2000.0]
    monkeypatch.setattr("time.time", lambda: fake_time[0])
    call_count = 0

    async def compute():
        nonlocal call_count
        call_count += 1
        return call_count

    first = await cache.get_or_compute("k", compute)
    fake_time[0] += 1.1
    second = await cache.get_or_compute("k", compute)

    assert first == 1
    assert second == 2


@pytest.mark.asyncio
async def test_get_or_compute_never_calls_compute_speculatively():
    cache = TTLCache()
    cache.set("k", "already-cached")

    async def compute():
        raise AssertionError("compute must not run on a cache hit")

    result = await cache.get_or_compute("k", compute)
    assert result == "already-cached"


def test_default_ttl_used_when_ttl_seconds_omitted(monkeypatch):
    cache = TTLCache(default_ttl_seconds=10)
    fake_time = [3000.0]
    monkeypatch.setattr("time.time", lambda: fake_time[0])

    cache.set("k", "v")
    fake_time[0] += 9.9
    assert cache.get("k") == "v"
    fake_time[0] += 0.2
    from src.market_data.caching.ttl_cache import _MISSING

    assert cache.get("k") is _MISSING
