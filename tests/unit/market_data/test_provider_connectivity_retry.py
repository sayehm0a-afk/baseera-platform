"""Unit tests for src.market_data.provider_connectivity_retry -- the
bounded retry/backoff wrapper around a SAHMK provider's connectivity
probe. Exercises every scenario the retry policy must handle correctly:
transient failures (timeout, 429, 5xx-shaped network error) are retried
up to a bounded attempt count with backoff; permanent failures (401,
403-as-authenticated already handled by the caller, missing key, an
open circuit breaker, a malformed response) are never retried.
"""

import asyncio

import pytest

from datetime import datetime, timezone

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.provider_connectivity_retry import (
    ProviderProbeTimeoutError,
    probe_connectivity_with_retry,
)
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkDailyQuotaExhaustedError,
    SahmkRateLimitError,
    SahmkRequestError,
    SahmkResponseValidationError,
)
from src.market_data.sahmk.rate_limiter import SahmkUpstreamQuotaExhaustedError


@pytest.fixture(autouse=True)
def _fast_retry_config(monkeypatch):
    # Bounded, fast, deterministic: real production defaults (3
    # attempts, 1s base delay) would make this test file slow. Jitter
    # is still exercised (base_delay > 0), just small.
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("SAHMK_PROBE_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("SAHMK_PROBE_RETRY_BASE_DELAY_SECONDS", "0.01")
    monkeypatch.setenv("SAHMK_PROBE_RETRY_MAX_DELAY_SECONDS", "0.05")
    yield


def _calls_then(*outcomes):
    """Returns a zero-arg callable that yields a fresh coroutine per
    call, replaying `outcomes` in order (an outcome is either a return
    value or an Exception instance to raise)."""
    remaining = list(outcomes)

    async def _call():
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return _call


@pytest.mark.asyncio
async def test_succeeds_on_first_attempt_with_no_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        return True

    result = await probe_connectivity_with_retry(_check, provider_label="test")
    assert result is True
    assert call_count == 1


@pytest.mark.asyncio
async def test_timeout_then_succeeds():
    calls = {"n": 0}

    async def _check():
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(10)  # exceeds the 0.2s per-attempt timeout
        return True

    result = await probe_connectivity_with_retry(_check, provider_label="test")
    assert result is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_429_then_succeeds_honoring_retry_after():
    fn = _calls_then(SahmkRateLimitError("rate limited", retry_after=0.02), True)

    result = await probe_connectivity_with_retry(fn, provider_label="test")
    assert result is True


@pytest.mark.asyncio
async def test_503_shaped_network_error_then_succeeds():
    # SahmkClient's _request() translates an exhausted 5xx/network
    # retry into SahmkRequestError with status_code=None (see
    # client.py) -- that's the exact shape a "connection reset" or
    # "SAHMK server error (503)" produces after its own internal
    # tenacity retries are exhausted.
    fn = _calls_then(
        SahmkRequestError("SAHMK server error (503): service unavailable"), True
    )

    result = await probe_connectivity_with_retry(fn, provider_label="test")
    assert result is True


@pytest.mark.asyncio
async def test_permanent_401_does_not_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkAuthenticationError("invalid key", status_code=401)

    with pytest.raises(SahmkAuthenticationError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1


@pytest.mark.asyncio
async def test_permanent_business_4xx_does_not_retry():
    """A genuine, deterministic non-2xx response (e.g. 400/404) --
    distinguished from an exhausted-retry SahmkRequestError by having a
    real status_code set (see client.py's _handle_response, the only
    path that sets it)."""
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkRequestError("SAHMK request failed with status 404.", status_code=404)

    with pytest.raises(SahmkRequestError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1


@pytest.mark.asyncio
async def test_missing_api_key_configuration_error_does_not_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkConfigurationError("SAHMK_API_KEY is not configured.")

    with pytest.raises(SahmkConfigurationError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1


@pytest.mark.asyncio
async def test_open_circuit_breaker_does_not_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise CircuitBreakerOpenError("circuit is open")

    with pytest.raises(CircuitBreakerOpenError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1


@pytest.mark.asyncio
async def test_response_validation_error_does_not_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkResponseValidationError("missing required field")

    with pytest.raises(SahmkResponseValidationError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1


@pytest.mark.asyncio
async def test_all_retries_exhausted_raises_probe_timeout_error():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(10)
        return True

    with pytest.raises(ProviderProbeTimeoutError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 3  # SAHMK_PROBE_MAX_ATTEMPTS from the fixture


@pytest.mark.asyncio
async def test_all_retries_exhausted_on_repeated_transient_request_error():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    with pytest.raises(SahmkRequestError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 3


# --- daily-quota exhaustion: never retried (2026-08-10 production evidence) -
# A real 429 "Daily rate limit exceeded (5000 requests/day)" means
# hours, not seconds, until recovery -- retrying it here would just be
# another wasted request/backoff-sleep against a known-exhausted
# budget. Both the exception client.py raises on a fresh 429 AND the
# one SahmkRateLimiter raises when a *different* caller already
# recorded that same evidence must short-circuit identically.


@pytest.mark.asyncio
async def test_daily_quota_exhausted_error_does_not_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkDailyQuotaExhaustedError(
            "SAHMK daily quota exhausted (429): Daily rate limit exceeded (5000 requests/day). "
            "Expected available in 54711 seconds.",
            retry_after_seconds=54711,
        )

    with pytest.raises(SahmkDailyQuotaExhaustedError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1


@pytest.mark.asyncio
async def test_upstream_quota_exhausted_error_does_not_retry():
    call_count = 0

    async def _check():
        nonlocal call_count
        call_count += 1
        raise SahmkUpstreamQuotaExhaustedError(
            "SAHMK's real daily quota is confirmed exhausted.",
            reset_at_utc=datetime.now(timezone.utc),
            evidence="Daily rate limit exceeded (5000 requests/day).",
        )

    with pytest.raises(SahmkUpstreamQuotaExhaustedError):
        await probe_connectivity_with_retry(_check, provider_label="test")
    assert call_count == 1
