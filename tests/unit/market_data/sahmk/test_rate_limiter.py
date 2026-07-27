"""Unit tests for SahmkRateLimiter. Real wall-clock sleeps are avoided
throughout -- either by staying under the configured limit, or by
monkeypatching asyncio.sleep and asserting it was awaited with roughly
the expected wait duration instead of actually waiting."""

import asyncio
import time

import pytest

from src.market_data.sahmk.rate_limiter import (
    SahmkRateLimitExceededError,
    SahmkRateLimiter,
    get_default_rate_limiter,
    reset_default_rate_limiter,
)


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
