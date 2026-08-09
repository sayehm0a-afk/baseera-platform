"""Unit tests for SahmkRateLimiter. Real wall-clock sleeps are avoided
throughout -- either by staying under the configured limit, or by
monkeypatching asyncio.sleep and asserting it was awaited with roughly
the expected wait duration instead of actually waiting."""

import asyncio
import time

import pytest

from src.market_data.sahmk.rate_limiter import (
    SahmkQuotaReservedForCriticalError,
    SahmkRateLimitExceededError,
    SahmkRateLimiter,
    get_default_rate_limiter,
    reset_default_rate_limiter,
)
from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL


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
