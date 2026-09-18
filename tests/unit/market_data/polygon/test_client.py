"""Unit tests for PolygonClient. No real network call is ever made --
every test injects a FakeSession replaying pre-built responses.
Mirrors tests/unit/market_data/sahmk/test_client.py's style and
coverage depth."""

import asyncio
from datetime import date

import aiohttp
import pytest

from src.core.runtime.reliability_layer.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from src.market_data.polygon.client import PolygonClient
from src.market_data.polygon.exceptions import (
    PolygonAuthenticationError,
    PolygonConfigurationError,
    PolygonRateLimitError,
    PolygonRequestError,
)
from src.market_data.polygon.rate_limiter import PolygonRateLimiter
from src.market_data.validators.symbol_validator import InvalidSymbolError
from tests.unit.market_data.polygon._fakes import FakeResponse, FakeSession


def _client(outcomes, **kwargs):
    session = FakeSession(outcomes)
    defaults = dict(
        api_key="test-key",
        base_url="https://polygon.example.invalid",
        session=session,
        # Effectively unlimited: these tests exercise error-mapping/
        # retry/circuit-breaker behavior, not the rate limiter (see
        # test_rate_limiter.py for that) -- and MUST NOT share the real
        # process-wide default limiter, whose internal usage window
        # would otherwise accumulate across every test in this file.
        rate_limiter=PolygonRateLimiter(max_per_minute=1_000_000),
    )
    defaults.update(kwargs)
    client = PolygonClient(**defaults)
    return client, session


@pytest.fixture(autouse=True)
def _instant_retry_sleep(monkeypatch):
    """Retries are exercised for real (via tenacity) in several tests
    below; patching asyncio.sleep keeps them from taking 0.5s-2s each."""

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


# --- construction / credentials -- never crashes, never dials out ----------


def test_construction_with_no_api_key_does_not_raise():
    client = PolygonClient(api_key=None, base_url="https://polygon.example.invalid")
    assert client.has_credentials is False


def test_has_credentials_true_when_api_key_provided():
    client, _ = _client([])
    assert client.has_credentials is True


def test_has_credentials_false_when_no_key_and_no_env(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    client, _ = _client([], api_key=None)
    assert client.has_credentials is False


@pytest.mark.asyncio
async def test_request_raises_configuration_error_only_when_a_method_is_called(monkeypatch):
    """PolygonConfigurationError must never be raised at construction --
    only once a method that actually needs the network is invoked."""
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    client, session = _client([], api_key=None)  # construction: no raise
    with pytest.raises(PolygonConfigurationError):
        await client.get_market_status()
    assert session.calls == []  # never reached the network


# --- successful wrapper calls: endpoint, headers, params -----------------


@pytest.mark.asyncio
async def test_get_previous_close_calls_correct_endpoint_with_bearer_header():
    client, session = _client([FakeResponse(200, {"results": [{"c": 150.0}]})])
    result = await client.get_previous_close("AAPL")
    assert result == {"results": [{"c": 150.0}]}
    assert session.calls[0]["url"] == "https://polygon.example.invalid/v2/aggs/ticker/AAPL/prev"
    assert session.calls[0]["headers"] == {"Authorization": "Bearer test-key"}


@pytest.mark.asyncio
async def test_get_previous_close_rejects_a_tadawul_style_4_digit_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_previous_close("1120")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_previous_close_rejects_lowercase_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_previous_close("aapl")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_aggregates_calls_correct_endpoint_with_params():
    client, session = _client([FakeResponse(200, {"results": []})])
    await client.get_aggregates(
        "AAPL", 1, "day", date(2026, 1, 1), date(2026, 1, 31), adjusted=True, sort="asc", limit=100
    )
    assert (
        session.calls[0]["url"]
        == "https://polygon.example.invalid/v2/aggs/ticker/AAPL/range/1/day/2026-01-01/2026-01-31"
    )
    assert session.calls[0]["params"] == {"adjusted": "true", "sort": "asc", "limit": 100}


@pytest.mark.asyncio
async def test_get_aggregates_accepts_string_dates():
    client, session = _client([FakeResponse(200, {"results": []})])
    await client.get_aggregates("AAPL", 1, "day", "2026-01-01", "2026-01-31")
    assert (
        session.calls[0]["url"]
        == "https://polygon.example.invalid/v2/aggs/ticker/AAPL/range/1/day/2026-01-01/2026-01-31"
    )


@pytest.mark.asyncio
async def test_get_aggregates_rejects_malformed_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_aggregates("2222", 1, "day", date(2026, 1, 1), date(2026, 1, 2))
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_ticker_details_calls_correct_endpoint():
    client, session = _client([FakeResponse(200, {"results": {"ticker": "AAPL"}})])
    result = await client.get_ticker_details("AAPL")
    assert result == {"results": {"ticker": "AAPL"}}
    assert session.calls[0]["url"] == "https://polygon.example.invalid/v3/reference/tickers/AAPL"


@pytest.mark.asyncio
async def test_get_ticker_details_rejects_malformed_symbol():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_ticker_details("not-a-symbol")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_tickers_calls_correct_endpoint_with_defaults():
    client, session = _client([FakeResponse(200, {"results": [{"ticker": "AAPL"}]})])
    result = await client.get_tickers()
    assert result == {"results": [{"ticker": "AAPL"}], "count": 1}
    assert session.calls[0]["url"] == "https://polygon.example.invalid/v3/reference/tickers"
    assert session.calls[0]["params"] == {"market": "stocks", "active": "true"}


@pytest.mark.asyncio
async def test_get_tickers_follows_next_url_pagination():
    client, session = _client(
        [
            FakeResponse(
                200,
                {
                    "results": [{"ticker": "AAPL"}],
                    "next_url": "https://api.polygon.io/v3/reference/tickers?cursor=abc123",
                },
            ),
            FakeResponse(200, {"results": [{"ticker": "MSFT"}]}),
        ]
    )
    result = await client.get_tickers()
    assert result == {"results": [{"ticker": "AAPL"}, {"ticker": "MSFT"}], "count": 2}
    assert len(session.calls) == 2
    assert session.calls[1]["params"] == {"cursor": "abc123"}


@pytest.mark.asyncio
async def test_get_tickers_stops_when_no_next_url():
    client, session = _client([FakeResponse(200, {"results": [{"ticker": "AAPL"}]})])
    await client.get_tickers()
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_get_tickers_bounded_pagination_never_spins_forever():
    """A next_url that keeps reporting a further page must still stop
    at _MAX_TICKER_PAGES, never loop unboundedly."""
    import src.market_data.polygon.client as client_module

    outcomes = [
        FakeResponse(
            200,
            {
                "results": [{"ticker": f"T{i}"}],
                "next_url": f"https://api.polygon.io/v3/reference/tickers?cursor={i}",
            },
        )
        for i in range(client_module._MAX_TICKER_PAGES + 5)
    ]
    client, session = _client(outcomes)
    result = await client.get_tickers()
    assert len(session.calls) == client_module._MAX_TICKER_PAGES
    assert result["count"] == client_module._MAX_TICKER_PAGES


@pytest.mark.asyncio
async def test_get_ticker_news_sends_limit_and_ticker_params():
    client, session = _client([FakeResponse(200, {"results": []})])
    await client.get_ticker_news(ticker="AAPL", limit=5)
    assert session.calls[0]["url"] == "https://polygon.example.invalid/v2/reference/news"
    assert session.calls[0]["params"] == {"limit": 5, "ticker": "AAPL"}


@pytest.mark.asyncio
async def test_get_ticker_news_without_ticker_omits_ticker_param():
    client, session = _client([FakeResponse(200, {"results": []})])
    await client.get_ticker_news(limit=10)
    assert session.calls[0]["params"] == {"limit": 10}


@pytest.mark.asyncio
async def test_get_ticker_news_rejects_malformed_ticker():
    client, session = _client([])
    with pytest.raises(InvalidSymbolError):
        await client.get_ticker_news(ticker="1120")
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_market_status_calls_correct_endpoint():
    client, session = _client([FakeResponse(200, {"market": "open"})])
    result = await client.get_market_status()
    assert result == {"market": "open"}
    assert session.calls[0]["url"] == "https://polygon.example.invalid/v1/marketstatus/now"


# --- status-code -> exception mapping -------------------------------------


@pytest.mark.asyncio
async def test_401_raises_authentication_error():
    client, _ = _client([FakeResponse(401, {"status": "ERROR", "message": "Unknown API Key"})])
    with pytest.raises(PolygonAuthenticationError) as exc_info:
        await client.get_market_status()
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_403_raises_authentication_error():
    client, _ = _client([FakeResponse(403, {"status": "ERROR", "message": "Forbidden"})])
    with pytest.raises(PolygonAuthenticationError) as exc_info:
        await client.get_market_status()
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_401_is_never_retried():
    client, session = _client([FakeResponse(401, {"message": "bad key"})] * 3)
    with pytest.raises(PolygonAuthenticationError):
        await client.get_market_status()
    assert len(session.calls) == 1  # never retried, unlike a 429/5xx


@pytest.mark.asyncio
async def test_403_is_never_retried():
    client, session = _client([FakeResponse(403, {"message": "forbidden"})] * 3)
    with pytest.raises(PolygonAuthenticationError):
        await client.get_market_status()
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_other_4xx_raises_generic_request_error():
    client, _ = _client([FakeResponse(404, {"error": "not found"})])
    with pytest.raises(PolygonRequestError) as exc_info:
        await client.get_market_status()
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_non_json_200_response_raises_request_error():
    client, _ = _client([FakeResponse(200, text_body="<html>not json</html>", raise_on_json=True)])
    with pytest.raises(PolygonRequestError):
        await client.get_market_status()


@pytest.mark.asyncio
async def test_network_error_is_retried_and_recovers_on_second_attempt():
    client, session = _client(
        [aiohttp.ClientConnectionError("connection refused"), FakeResponse(200, {"market": "open"})]
    )
    result = await client.get_market_status()
    assert result == {"market": "open"}
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_network_error_raises_request_error_after_retries_exhausted():
    client, session = _client([aiohttp.ClientConnectionError("connection refused")] * 3)
    with pytest.raises(PolygonRequestError):
        await client.get_market_status()
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_timeout_error_is_retried_like_a_network_error():
    client, session = _client([asyncio.TimeoutError(), FakeResponse(200, {"market": "open"})])
    result = await client.get_market_status()
    assert result == {"market": "open"}
    assert len(session.calls) == 2


# --- retry behavior: 429 and 5xx --------------------------------------


@pytest.mark.asyncio
async def test_5xx_is_retried_and_recovers_on_second_attempt():
    client, session = _client(
        [FakeResponse(503, {"error": "unavailable"}), FakeResponse(200, {"market": "open"})]
    )
    result = await client.get_market_status()
    assert result == {"market": "open"}
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_5xx_raises_request_error_after_retries_exhausted():
    client, session = _client([FakeResponse(500, {})] * 3)
    with pytest.raises(PolygonRequestError):
        await client.get_market_status()
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_429_raises_rate_limit_error_after_retries_exhausted_and_reports_retry_after():
    client, session = _client([FakeResponse(429, {}, headers={"Retry-After": "3"})] * 3)
    with pytest.raises(PolygonRateLimitError) as exc_info:
        await client.get_market_status()
    assert exc_info.value.retry_after == 3.0
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_429_recovers_once_rate_limit_clears():
    client, session = _client([FakeResponse(429, {}), FakeResponse(200, {"market": "open"})])
    result = await client.get_market_status()
    assert result == {"market": "open"}


# --- circuit breaker -------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(500, {})] * 3, circuit_breaker=breaker)
    with pytest.raises(PolygonRequestError):
        await client.get_market_status()

    with pytest.raises(CircuitBreakerOpenError):
        await client.get_market_status()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_429_exhaustion():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(429, {})] * 3, circuit_breaker=breaker)
    with pytest.raises(PolygonRateLimitError):
        await client.get_market_status()

    with pytest.raises(CircuitBreakerOpenError):
        await client.get_market_status()


# --- regression: business errors must never trip the circuit breaker -------


@pytest.mark.asyncio
async def test_repeated_401_never_opens_the_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(401, {"message": "bad key"})] * 5, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(PolygonAuthenticationError):
            await client.get_market_status()

    assert breaker.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_repeated_403_never_opens_the_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(403, {"message": "forbidden"})] * 5, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(PolygonAuthenticationError):
            await client.get_market_status()

    assert breaker.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_repeated_other_4xx_never_opens_the_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    client, session = _client([FakeResponse(404, {"error": "not found"})] * 5, circuit_breaker=breaker)

    for _ in range(5):
        with pytest.raises(PolygonRequestError):
            await client.get_market_status()

    assert breaker.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_repeated_auth_errors_do_not_block_a_different_healthy_endpoint():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    outcomes = [FakeResponse(401, {"message": "bad key"})] * 3 + [FakeResponse(200, {"market": "open"})]
    client, session = _client(outcomes, circuit_breaker=breaker)

    for _ in range(3):
        with pytest.raises(PolygonAuthenticationError):
            await client.get_market_status()

    result = await client.get_market_status()
    assert result == {"market": "open"}


@pytest.mark.asyncio
async def test_mixed_business_and_infrastructure_failures_only_the_infrastructure_one_counts():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
    outcomes = (
        [FakeResponse(401, {"message": "bad key"})] * 3  # must never move the breaker at all
        + [FakeResponse(500, {})] * 3  # one genuine failure (after exhausting its own retries) -- opens it
    )
    client, session = _client(outcomes, circuit_breaker=breaker)

    for _ in range(3):
        with pytest.raises(PolygonAuthenticationError):
            await client.get_market_status()
    assert breaker.state.value == "CLOSED"

    with pytest.raises(PolygonRequestError):
        await client.get_market_status()

    with pytest.raises(CircuitBreakerOpenError):
        await client.get_market_status()


# --- rate limiter integration -----------------------------------------------


@pytest.mark.asyncio
async def test_request_acquires_a_rate_limiter_slot_before_dispatching():
    from unittest.mock import AsyncMock

    limiter = AsyncMock()
    client, session = _client([FakeResponse(200, {"market": "open"})], rate_limiter=limiter)
    await client.get_market_status()
    limiter.acquire.assert_awaited_once()


# --- session lifecycle -----------------------------------------------------


@pytest.mark.asyncio
async def test_close_closes_owned_session():
    session = FakeSession([])
    client = PolygonClient(api_key="k", base_url="https://x.invalid", session=session)
    await client.close()
    assert session.closed is False  # session was injected, not owned by the client


@pytest.mark.asyncio
async def test_async_context_manager_closes_owned_session_on_exit():
    async with PolygonClient(api_key="k", base_url="https://x.invalid") as client:
        session = await client._ensure_session()
        assert session.closed is False
    assert session.closed is True
