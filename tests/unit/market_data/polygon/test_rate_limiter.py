"""Unit tests for PolygonRateLimiter. Real wall-clock sleeps are avoided
throughout -- either by staying under the configured limit, or by
monkeypatching asyncio.sleep and asserting it was awaited with roughly
the expected wait duration instead of actually waiting. Mirrors
tests/unit/market_data/sahmk/test_rate_limiter.py's style, scoped down
to the sliding-window-only mechanism PolygonRateLimiter actually has
(see that module's own docstring for why v1 has no daily/priority
tiers)."""

import asyncio
import time

import pytest

from src.market_data.polygon.rate_limiter import (
    PolygonRateLimiter,
    get_default_polygon_rate_limiter,
    reset_default_polygon_rate_limiter,
)


def test_rejects_non_positive_max_per_minute():
    with pytest.raises(ValueError):
        PolygonRateLimiter(max_per_minute=0)


def test_rejects_negative_max_per_minute():
    with pytest.raises(ValueError):
        PolygonRateLimiter(max_per_minute=-1)


@pytest.mark.asyncio
async def test_acquire_succeeds_under_the_limit():
    limiter = PolygonRateLimiter(max_per_minute=5)
    for _ in range(5):
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

    limiter = PolygonRateLimiter(max_per_minute=2)
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # 3rd call exceeds the 2/minute cap -- must wait

    assert len(sleep_calls) == 1
    assert 0 < sleep_calls[0] <= 60


@pytest.mark.asyncio
async def test_acquire_evicts_expired_entries_and_admits_again(monkeypatch):
    fake_now = [1_000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    async def _fake_sleep(seconds):
        fake_now[0] += seconds

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    limiter = PolygonRateLimiter(max_per_minute=1)
    await limiter.acquire()
    fake_now[0] += 61.0  # window has fully rolled over
    await limiter.acquire()  # must not sleep -- the earlier entry already expired
    assert limiter.get_status()["requests_in_last_minute"] == 1


def test_get_status_reflects_configuration_and_zero_usage():
    limiter = PolygonRateLimiter(max_per_minute=5)
    status = limiter.get_status()
    assert status["max_per_minute"] == 5
    assert status["requests_in_last_minute"] == 0


@pytest.mark.asyncio
async def test_get_status_tracks_usage():
    limiter = PolygonRateLimiter(max_per_minute=5)
    await limiter.acquire()
    await limiter.acquire()
    assert limiter.get_status()["requests_in_last_minute"] == 2


def test_reset_clears_usage():
    limiter = PolygonRateLimiter(max_per_minute=5)
    limiter._minute_window.append(0.0)
    limiter.reset()
    assert list(limiter._minute_window) == []


# --- process-wide default singleton -----------------------------------------


def test_get_default_polygon_rate_limiter_returns_the_same_instance(monkeypatch):
    reset_default_polygon_rate_limiter()
    monkeypatch.setenv("POLYGON_MAX_REQUESTS_PER_MINUTE", "7")
    first = get_default_polygon_rate_limiter()
    second = get_default_polygon_rate_limiter()
    assert first is second
    assert first._max_per_minute == 7
    reset_default_polygon_rate_limiter()


def test_reset_default_polygon_rate_limiter_forces_a_fresh_instance(monkeypatch):
    reset_default_polygon_rate_limiter()
    monkeypatch.setenv("POLYGON_MAX_REQUESTS_PER_MINUTE", "3")
    first = get_default_polygon_rate_limiter()
    reset_default_polygon_rate_limiter()
    monkeypatch.setenv("POLYGON_MAX_REQUESTS_PER_MINUTE", "9")
    second = get_default_polygon_rate_limiter()
    assert first is not second
    assert second._max_per_minute == 9
    reset_default_polygon_rate_limiter()


def test_default_singleton_uses_the_documented_free_tier_default(monkeypatch):
    reset_default_polygon_rate_limiter()
    monkeypatch.delenv("POLYGON_MAX_REQUESTS_PER_MINUTE", raising=False)
    limiter = get_default_polygon_rate_limiter()
    assert limiter._max_per_minute == 5
    reset_default_polygon_rate_limiter()
