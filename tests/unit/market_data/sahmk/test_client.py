"""Unit tests for SahmkClient. No real network call is ever made -- every
test injects a FakeSession replaying pre-built responses. Endpoints,
headers, and status-code mapping asserted here match the verified
contract in docs/SAHMK_INTEGRATION.md."""

import asyncio
from datetime import date

import aiohttp
import pytest

import src.market_data.sahmk.rate_limiter as rate_limiter_module
from src.core.runtime.reliability_layer.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from src.market_data.sahmk.client import SahmkClient
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkEntitlementError,
    SahmkRateLimitError,
    SahmkRequestError,
)
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter
from src.market_data.validators.symbol_validator import InvalidSymbolError
from tests.unit.market_data.sahmk._fakes import FakeResponse, FakeSession


def _client(outcomes, **kwargs):
    session = FakeSession(outcomes)
    defaults = dict(
        api_key="test-key",
        base_url="https://sahmk.example.invalid",
        session=session,
        # Effectively unlimited: these tests exercise error-mapping/retry/
        # circuit-breaker behavior, not the rate limiter (see
        # test_rate_limiter.py for that) -- and MUST NOT share the real
        # process-wide default limiter, whose internal usage window
        # would otherwise accumulate across every test in this file.
        rate_limiter=SahmkRateLimiter(max_per_minute=1_000_000),
    )
    defaults.update(kwargs)
    client = SahmkClient(**defaults)
    return client, session


@pytest.fixture(autouse=True)
def _instant_retry_sleep(monkeypatch):
    """Retries are exercised for real (via tenacity) in several tests
    below; patching asyncio.sleep keeps them from taking 0.5s-2s each."""

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


@pytest.fixture(autouse=True)
def _no_real_shared_redis_by_default(monkeypatch):
    """_client()'s default SahmkRateLimiter (like most in this file)
    passes no redis_client= override, which means "use the process-
    wide shared singleton" -- fine when no real Redis is reachable
    (this repo's local dev sandbox), but a real regression in any
    environment that actually provisions one (CI does): one test's
    real 429 would persist SAHMK daily-quota-exhaustion evidence into
    that shared Redis, poisoning every other test in this file that
    constructs a limiter afterward. See test_rate_limiter.py's
    identical fixture for the full 2026-08-10 production incident this
    guards against."""
    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)


# --- construction / credentials -----------------------------------------


def test_has_credentials_true_when_api_key_provided():
    client, _ = _client([])
    assert client.has_credentials is True


def test_has_credentials_false_when_no_key_and_no_env(monkeypatch):
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    client, _ = _client([], api_key=None)
    assert client.has_credentials is False


@pytest.mark.asyncio
async def test_request_raises_configuration_error_when_no_key(monkeypatch):
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    client, session = _client([], api_key=None)
    with pytest.raises(SahmkConfigurationError):
        await client.get_market_summary("TASI")
    assert session.calls == []


# --- successful wrapper calls: endpoint, headers, params -----------------


@pytest.mark.asyncio
async def test_get_quote_calls_correct_endpoint_with_api_key_header():
    client, session = _client([FakeResponse(200, {"price": 42.5})])
    result = await client.get_quote("1120")
    assert result == {"price": 42.5}
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/quote/1120/"
    assert session.calls[0]["headers"] == {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_get_quote_rejects_malformed_symbol_before_any_request():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_quote("AAPL")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_historical_sends_interval_and_date_range():
    client, session = _client([FakeResponse(200, {"bars": []})])
    await client.get_historical(
        "2222", interval="1d", date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)
    )
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/historical/2222/"
    assert session.calls[0]["params"] == {"interval": "1d", "from": "2026-01-01", "to": "2026-01-31"}


@pytest.mark.asyncio
async def test_get_historical_rejects_malformed_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_historical("not-a-symbol")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_market_summary_defaults_to_tasi():
    client, session = _client([FakeResponse(200, {"index_value": 12000})])
    result = await client.get_market_summary()
    assert result == {"index_value": 12000}
    assert session.calls[0]["params"] == {"index": "TASI"}


@pytest.mark.asyncio
async def test_get_events_sends_limit_param():
    client, session = _client([FakeResponse(200, {"events": []})])
    await client.get_events(limit=5)
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/events/"
    assert session.calls[0]["params"] == {"limit": 5}


@pytest.mark.asyncio
async def test_get_company_profile_calls_correct_endpoint():
    client, session = _client([FakeResponse(200, {"name": "Aramco"})])
    result = await client.get_company_profile("2222")
    assert result == {"name": "Aramco"}
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/company/2222/"


@pytest.mark.asyncio
async def test_get_company_profile_rejects_malformed_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_company_profile("AAPL")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_financials_calls_correct_endpoint_with_period():
    client, session = _client([FakeResponse(200, {"revenue": 1})])
    result = await client.get_financials("2222", period_type="quarterly")
    assert result == {"revenue": 1}
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/financials/2222/"
    assert session.calls[0]["params"] == {"period": "quarterly"}


@pytest.mark.asyncio
async def test_get_financials_rejects_malformed_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_financials("AAPL")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_dividends_calls_correct_endpoint():
    client, session = _client([FakeResponse(200, {"dividends": []})])
    result = await client.get_dividends("2222")
    assert result == {"dividends": []}
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/dividends/2222/"


@pytest.mark.asyncio
async def test_get_dividends_rejects_malformed_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_dividends("AAPL")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_companies_calls_correct_endpoint():
    client, session = _client([FakeResponse(200, {"companies": []})])
    result = await client.get_companies()
    assert result == {"companies": []}
    assert session.calls[0]["url"] == "https://sahmk.example.invalid/companies/"
    assert session.calls[0]["params"] is None


# --- status-code -> exception mapping -------------------------------------


@pytest.mark.asyncio
async def test_401_raises_authentication_error():
    client, _ = _client([FakeResponse(401, {"error": "invalid key"})])
    with pytest.raises(SahmkAuthenticationError) as exc_info:
        await client.get_market_summary("TASI")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_403_raises_entitlement_error_with_body():
    client, _ = _client([FakeResponse(403, {"error": "PLAN_LIMIT"})])
    with pytest.raises(SahmkEntitlementError) as exc_info:
        await client.get_events(limit=10)
    assert exc_info.value.status_code == 403
    assert exc_info.value.body == {"error": "PLAN_LIMIT"}


@pytest.mark.asyncio
async def test_other_4xx_raises_generic_request_error():
    client, _ = _client([FakeResponse(404, {"error": "not found"})])
    with pytest.raises(SahmkRequestError) as exc_info:
        await client.get_market_summary("TASI")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_non_json_200_response_raises_request_error():
    client, _ = _client([FakeResponse(200, text_body="<html>not json</html>", raise_on_json=True)])
    with pytest.raises(SahmkRequestError):
        await client.get_market_summary("TASI")


@pytest.mark.asyncio
async def test_network_error_is_retried_and_recovers_on_second_attempt():
    # A connection failure/timeout is exactly as transient as a 5xx
    # (found in the pre-live-scan production audit: it previously
    # was NOT retried, unlike a 500, which meant one slow/dropped
    # connection failed a symbol outright during a real full-market
    # scan while an otherwise-identical 500 would recover). Must be
    # retried the same way 5xx already is.
    client, session = _client(
        [aiohttp.ClientConnectionError("connection refused"), FakeResponse(200, {"index_value": 1})]
    )
    result = await client.get_market_summary("TASI")
    assert result == {"index_value": 1}
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_network_error_raises_request_error_after_retries_exhausted():
    client, session = _client([aiohttp.ClientConnectionError("connection refused")] * 3)
    with pytest.raises(SahmkRequestError):
        await client.get_market_summary("TASI")
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_timeout_error_is_retried_like_a_network_error():
    client, session = _client([asyncio.TimeoutError(), FakeResponse(200, {"index_value": 1})])
    result = await client.get_market_summary("TASI")
    assert result == {"index_value": 1}
    assert len(session.calls) == 2


# --- retry behavior: 429 and 5xx --------------------------------------


@pytest.mark.asyncio
async def test_5xx_is_retried_and_recovers_on_second_attempt():
    client, session = _client(
        [FakeResponse(503, {"error": "unavailable"}), FakeResponse(200, {"index_value": 1})]
    )
    result = await client.get_market_summary("TASI")
    assert result == {"index_value": 1}
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_5xx_raises_request_error_after_retries_exhausted():
    client, session = _client([FakeResponse(500, {})] * 3)
    with pytest.raises(SahmkRequestError):
        await client.get_market_summary("TASI")
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_429_raises_rate_limit_error_after_retries_exhausted_and_reports_retry_after():
    client, session = _client([FakeResponse(429, {}, headers={"Retry-After": "3"})] * 3)
    with pytest.raises(SahmkRateLimitError) as exc_info:
        await client.get_market_summary("TASI")
    assert exc_info.value.retry_after == 3.0
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_429_recovers_once_rate_limit_clears():
    client, session = _client([FakeResponse(429, {}), FakeResponse(200, {"index_value": 5})])
    result = await client.get_market_summary("TASI")
    assert result == {"index_value": 5}


# --- daily-quota exhaustion: a distinct, evidence-based outcome -------------
# 2026-08-10 production evidence: SAHMK's real 429 body for a *daily*
# exhaustion reads "Daily rate limit exceeded (5000 requests/day)...
# Expected available in N seconds" -- distinguished from an ordinary
# short-lived 429 (which stays SahmkRateLimitError/_RetryableSahmkError,
# retried as before) so it is never retried and is recorded as real
# quota-exhaustion evidence for every other caller/worker to see.


@pytest.mark.asyncio
async def test_daily_quota_429_raises_immediately_without_retrying():
    from src.market_data.sahmk.exceptions import SahmkDailyQuotaExhaustedError

    client, session = _client(
        [
            FakeResponse(
                429,
                {
                    "detail": (
                        "Daily rate limit exceeded (5000 requests/day). Resets at midnight. "
                        "Upgrade: https://www.sahmk.sa/developers/pricing "
                        "Expected available in 54711 seconds."
                    )
                },
            )
        ]
    )
    with pytest.raises(SahmkDailyQuotaExhaustedError) as exc_info:
        await client.get_market_summary("TASI")
    assert len(session.calls) == 1  # never retried, unlike an ordinary 429
    assert exc_info.value.retry_after_seconds == 54711.0


@pytest.mark.asyncio
async def test_daily_quota_429_is_a_rate_limit_error_for_backward_compatibility():
    """Existing callers written against the broader SahmkRateLimitError
    (provider_connectivity_retry.py's generic except clause, before its
    own more specific daily-quota clause) must still recognize this."""
    from src.market_data.sahmk.exceptions import SahmkDailyQuotaExhaustedError

    client, session = _client(
        [FakeResponse(429, {"detail": "Daily rate limit exceeded (5000 requests/day)."})]
    )
    with pytest.raises(SahmkRateLimitError):
        await client.get_market_summary("TASI")
    assert issubclass(SahmkDailyQuotaExhaustedError, SahmkRateLimitError)


@pytest.mark.asyncio
async def test_daily_quota_429_does_not_trip_the_circuit_breaker():
    """A real daily-quota answer means SAHMK is healthy and reachable --
    our account is just out of budget. Unlike a genuine 429 exhaustion
    (test_circuit_breaker_opens_after_repeated_429_exhaustion above),
    this must never count as a breaker failure -- otherwise every other
    unrelated call on the same client would also be blocked for
    recovery_timeout, on top of the real multi-hour quota wait."""
    from src.market_data.sahmk.exceptions import SahmkDailyQuotaExhaustedError
    from src.market_data.sahmk.rate_limiter import SahmkUpstreamQuotaExhaustedError

    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client(
        [FakeResponse(429, {"detail": "Daily rate limit exceeded (5000 requests/day)."})] * 2,
        circuit_breaker=breaker,
    )
    with pytest.raises(SahmkDailyQuotaExhaustedError):
        await client.get_market_summary("TASI")
    # The first call's real 429 already recorded evidence on this
    # client's own rate limiter -- the second call never reaches the
    # network at all (short-circuited by acquire()), which is an even
    # stronger proof of "no request storm" than reaching SAHMK again.
    # If the breaker HAD tripped instead, this would raise
    # CircuitBreakerOpenError, not SahmkUpstreamQuotaExhaustedError.
    with pytest.raises(SahmkUpstreamQuotaExhaustedError):
        await client.get_market_summary("TASI")
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_daily_quota_429_records_evidence_on_the_rate_limiter():
    limiter = SahmkRateLimiter(max_per_minute=1_000_000, redis_client=None)
    client, session = _client(
        [FakeResponse(429, {"detail": "Daily rate limit exceeded (5000 requests/day). Expected available in 120 seconds."})],
        rate_limiter=limiter,
    )
    with pytest.raises(Exception):
        await client.get_market_summary("TASI")

    status = limiter.get_status()
    assert status["upstream_confirmed_exhausted"] is True
    assert "Daily rate limit exceeded" in status["upstream_exhaustion_evidence"]


@pytest.mark.asyncio
async def test_ordinary_429_without_daily_wording_is_still_retried_normally():
    """A short per-second/per-minute 429 (no "daily" wording at all)
    must keep using the existing retryable path -- this fix only
    changes behavior for a real, recognized daily-exhaustion body."""
    client, session = _client(
        [FakeResponse(429, {"detail": "Too many requests, slow down."}), FakeResponse(200, {"index_value": 7})]
    )
    result = await client.get_market_summary("TASI")
    assert result == {"index_value": 7}
    assert len(session.calls) == 2


# --- circuit breaker -------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures():
    """Regression guard: confirms the fix below did NOT neuter the
    breaker's real purpose -- genuine, repeated infrastructure failures
    (5xx surviving every retry) must still trip it."""
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(500, {})] * 3, circuit_breaker=breaker)
    with pytest.raises(SahmkRequestError):
        await client.get_market_summary("TASI")

    with pytest.raises(CircuitBreakerOpenError):
        await client.get_market_summary("TASI")


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_429_exhaustion():
    """429 exhaustion is transient/infrastructure in nature (the vendor
    is overloaded or we are), unlike a 401/403 -- it must still be able
    to trip the breaker."""
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(429, {})] * 3, circuit_breaker=breaker)
    with pytest.raises(SahmkRateLimitError):
        await client.get_market_summary("TASI")

    with pytest.raises(CircuitBreakerOpenError):
        await client.get_market_summary("TASI")


# --- regression: business errors must never trip the circuit breaker -------
#
# Reproduces the bug a prior review caught: three 403 PLAN_LIMIT responses
# on one (Pro+-only) endpoint tripped the shared client-wide breaker and
# blocked a completely unrelated, healthy call on the same client. 401,
# 403, and other deterministic non-2xx business responses are expected,
# routine outcomes from a reachable, healthy SAHMK -- never a sign the
# service is down -- and must never be treated as breaker failures.


@pytest.mark.asyncio
async def test_repeated_401_never_opens_the_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(401, {"error": "invalid key"})] * 5, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(SahmkAuthenticationError):
            await client.get_market_summary("TASI")

    assert breaker.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_repeated_403_entitlement_errors_never_open_the_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(403, {"error": "PLAN_LIMIT"})] * 5, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(SahmkEntitlementError):
            await client.get_events(limit=10)

    assert breaker.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_repeated_other_4xx_never_opens_the_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(404, {"error": "not found"})] * 5, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(SahmkRequestError):
            await client.get_market_summary("TASI")

    assert breaker.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_repeated_plan_limit_errors_do_not_block_a_different_healthy_endpoint():
    """The exact reproduction from the review: three 403 PLAN_LIMIT
    responses on get_events(), then a completely unrelated, healthy
    get_market_summary() call on the SAME client must still succeed."""
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    outcomes = [FakeResponse(403, {"error": "PLAN_LIMIT"})] * 3 + [FakeResponse(200, {"index_value": 12000})]
    client, session = _client(outcomes, circuit_breaker=breaker)

    for _ in range(3):
        with pytest.raises(SahmkEntitlementError):
            await client.get_events(limit=10)

    result = await client.get_market_summary("TASI")
    assert result == {"index_value": 12000}


@pytest.mark.asyncio
async def test_mixed_business_and_infrastructure_failures_only_the_infrastructure_one_counts():
    """A failure_threshold=1 breaker: if a business error counted for
    even a fraction of a "failure," it would open on the very first
    403. Three 403s in a row must leave it fully CLOSED; only the
    single genuine infrastructure failure that follows (a 500,
    exhausting its own retries) may open it."""
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    outcomes = (
        [FakeResponse(403, {"error": "PLAN_LIMIT"})] * 3  # must never move the breaker at all
        + [FakeResponse(500, {})] * 3  # one genuine failure (after exhausting its own retries) -- opens it
    )
    client, session = _client(outcomes, circuit_breaker=breaker)

    for _ in range(3):
        with pytest.raises(SahmkEntitlementError):
            await client.get_market_summary("TASI")
    assert breaker.state.value == "CLOSED"

    with pytest.raises(SahmkRequestError):
        await client.get_market_summary("TASI")

    with pytest.raises(CircuitBreakerOpenError):
        await client.get_market_summary("TASI")


# --- rate limiter integration -----------------------------------------------


@pytest.mark.asyncio
async def test_request_acquires_a_rate_limiter_slot_before_dispatching():
    from unittest.mock import AsyncMock

    limiter = AsyncMock()
    client, session = _client([FakeResponse(200, {"index_value": 1})], rate_limiter=limiter)
    await client.get_market_summary("TASI")
    limiter.acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_quota_exceeded_never_reaches_the_circuit_breaker():
    """SahmkRateLimitExceededError means "we decided not to call," not
    "SAHMK failed" -- it must never count as a circuit-breaker failure,
    the same reasoning _BusinessError exists for business responses."""
    from src.market_data.sahmk.rate_limiter import SahmkRateLimitExceededError

    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    limiter = SahmkRateLimiter(max_per_minute=10, max_per_day=1)
    client, session = _client(
        [FakeResponse(200, {"index_value": 1}), FakeResponse(200, {"index_value": 2})],
        rate_limiter=limiter,
        circuit_breaker=breaker,
    )

    await client.get_market_summary("TASI")  # spends the one daily slot
    with pytest.raises(SahmkRateLimitExceededError):
        await client.get_market_summary("TASI")

    # Breaker must still be CLOSED -- the quota refusal never touched it.
    assert breaker.state.value == "CLOSED"
    # The 2nd call's refusal raised before consuming any FakeSession
    # outcome (only 1 of the 2 queued outcomes was used), proving it
    # happened before any network call was attempted.
    assert len(session.calls) == 1


# --- session lifecycle -----------------------------------------------------


@pytest.mark.asyncio
async def test_close_closes_owned_session():
    session = FakeSession([])
    client = SahmkClient(api_key="k", base_url="https://x.invalid", session=session)
    await client.close()
    assert session.closed is False  # session was injected, not owned by the client


@pytest.mark.asyncio
async def test_async_context_manager_closes_owned_session_on_exit():
    async with SahmkClient(api_key="k", base_url="https://x.invalid") as client:
        session = await client._ensure_session()
        assert session.closed is False
    assert session.closed is True
