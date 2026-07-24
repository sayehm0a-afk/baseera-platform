"""Unit tests for SahmkMarketDataProvider.

No real SAHMK endpoint is contacted -- every test either mocks this
class's own `_request`/`session` boundary directly, or exercises the
credential-missing path, which by design never opens a socket at all.
Endpoints/fields asserted here match docs/SAHMK_INTEGRATION.md's
verified contract (X-API-Key header, no token exchange, /historical/
for OHLCV bars, /quote/ for live price only, /market/summary/ for
indices and health, /events/ for "market news").
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.models import MarketQuote
from src.market_data.providers.market_data_provider import (
    MarketDataProviderFactory,
    ProviderHealth,
)
from src.market_data.providers.sahmk_market_data_provider import (
    SahmkAuthenticationError,
    SahmkEntitlementError,
    SahmkMarketDataProvider,
    SahmkResponseValidationError,
    _SahmkRateLimitedError,
)
from src.market_data.validators.symbol_validator import InvalidSymbolError


def _provider(**kwargs):
    defaults = dict(api_endpoint="https://sahmk.example.invalid", api_key="key")
    defaults.update(kwargs)
    return SahmkMarketDataProvider(**defaults)


# --- authenticate() -----------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_fails_fast_when_credentials_missing():
    provider = SahmkMarketDataProvider(api_endpoint="", api_key="")
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_succeeds_via_market_summary_call():
    provider = _provider()
    provider._request = AsyncMock(return_value={"index_value": 12000, "index_change_percent": 0.5})
    result = await provider.authenticate()
    assert result is True
    assert provider.authenticated is True
    provider._request.assert_awaited_once_with("/market/summary/", params={"index": "TASI"})


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_rejected_key():
    provider = _provider()
    provider._request = AsyncMock(side_effect=SahmkAuthenticationError("bad key"))
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_treats_entitlement_error_as_valid_key():
    provider = _provider()
    provider._request = AsyncMock(side_effect=SahmkEntitlementError("plan limit"))
    result = await provider.authenticate()
    assert result is True
    assert provider.authenticated is True


@pytest.mark.asyncio
async def test_authenticate_returns_false_when_circuit_breaker_open():
    provider = _provider()
    provider._circuit_breaker.execute = AsyncMock(side_effect=CircuitBreakerOpenError())
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


# --- get_stock_data() : uses /historical/, not /quote/ -------------------


@pytest.mark.asyncio
async def test_get_stock_data_rejects_malformed_symbol_before_any_request():
    provider = _provider()
    provider._request = AsyncMock()
    with pytest.raises(InvalidSymbolError):
        await provider.get_stock_data("AAPL")
    provider._request.assert_not_called()


@pytest.mark.asyncio
async def test_get_stock_data_returns_last_bar_from_historical_endpoint():
    provider = _provider()
    provider._request = AsyncMock(
        return_value={
            "bars": [
                {"open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "timestamp": "2026-01-05T00:00:00Z"},
            ]
        }
    )

    result = await provider.get_stock_data("1010")

    assert result["symbol"] == "1010"
    assert result["close"] == 10.5
    endpoint_called = provider._request.call_args.args[0]
    assert endpoint_called == "/historical/1010/"


@pytest.mark.asyncio
async def test_get_stock_data_caches_result():
    provider = _provider()
    provider._request = AsyncMock(
        return_value={"bars": [{"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 5, "timestamp": "t"}]}
    )
    await provider.get_stock_data("1010")
    await provider.get_stock_data("1010")
    provider._request.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_stock_data_raises_when_no_bar_available():
    provider = _provider()
    provider._request = AsyncMock(return_value={"bars": []})
    with pytest.raises(SahmkResponseValidationError):
        await provider.get_stock_data("1010")


@pytest.mark.asyncio
async def test_get_stock_data_raises_on_incomplete_bar():
    provider = _provider()
    provider._request = AsyncMock(return_value={"bars": [{"close": 10}]})  # missing open/high/low/volume/timestamp
    with pytest.raises(SahmkResponseValidationError):
        await provider.get_stock_data("1010")


# --- get_historical_ohlcv() -----------------------------------------------


@pytest.mark.asyncio
async def test_get_historical_ohlcv_rejects_malformed_symbol():
    provider = _provider()
    provider._request = AsyncMock()
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(InvalidSymbolError):
        await provider.get_historical_ohlcv("BAD", start, end)
    provider._request.assert_not_called()


@pytest.mark.asyncio
async def test_get_historical_ohlcv_sends_expected_params():
    provider = _provider()
    provider._request = AsyncMock(return_value={"bars": []})
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)

    await provider.get_historical_ohlcv("1010", start, end)

    provider._request.assert_awaited_once_with(
        "/historical/1010/",
        params={"interval": "1d", "from": "2024-01-01", "to": "2024-01-31"},
    )


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_normalized_bars():
    provider = _provider()
    provider._request = AsyncMock(
        return_value={
            "bars": [
                {"open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "timestamp": "2024-01-01T00:00:00Z"},
                {"open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 200, "timestamp": "2024-01-02T00:00:00Z"},
            ]
        }
    )
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    bars = await provider.get_historical_ohlcv("1010", start, end)

    assert len(bars) == 2
    assert bars[0]["symbol"] == "1010"
    assert set(bars[0].keys()) == {"symbol", "open", "high", "low", "close", "volume", "timestamp"}


@pytest.mark.asyncio
async def test_get_historical_ohlcv_accepts_results_key_as_alternative_to_bars():
    provider = _provider()
    provider._request = AsyncMock(
        return_value={"results": [{"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 5, "timestamp": "t"}]}
    )
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = await provider.get_historical_ohlcv("1010", start, start)
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_get_historical_ohlcv_raises_on_bar_missing_required_field():
    provider = _provider()
    provider._request = AsyncMock(return_value={"bars": [{"open": 1, "close": 1.5}]})
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(SahmkResponseValidationError):
        await provider.get_historical_ohlcv("1010", start, start)


# --- get_latest_quote() : SAHMK-specific, not part of the ABC -----------


@pytest.mark.asyncio
async def test_get_latest_quote_rejects_malformed_symbol():
    provider = _provider()
    provider._request = AsyncMock()
    with pytest.raises(InvalidSymbolError):
        await provider.get_latest_quote("AAPL")
    provider._request.assert_not_called()


@pytest.mark.asyncio
async def test_get_latest_quote_returns_market_quote():
    provider = _provider()
    provider._request = AsyncMock(
        return_value={
            "symbol": "1010",
            "price": 42.5,
            "change": 1.2,
            "change_percent": 2.9,
            "volume": 100000,
            "value": 4250000,
            "name_en": "Riyad Bank",
        }
    )

    quote = await provider.get_latest_quote("1010")

    assert isinstance(quote, MarketQuote)
    assert quote.symbol == "1010"
    assert quote.price == 42.5
    assert quote.source == "sahmk"
    provider._request.assert_awaited_once_with("/quote/1010/")


@pytest.mark.asyncio
async def test_get_latest_quote_raises_on_missing_fields():
    provider = _provider()
    provider._request = AsyncMock(return_value={"symbol": "1010"})
    with pytest.raises(SahmkResponseValidationError):
        await provider.get_latest_quote("1010")


# --- get_index_data() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_data_rejects_unknown_index_name():
    provider = _provider()
    provider._request = AsyncMock()
    with pytest.raises(SahmkResponseValidationError):
        await provider.get_index_data("SP500")
    provider._request.assert_not_called()


@pytest.mark.asyncio
async def test_get_index_data_calls_market_summary():
    provider = _provider()
    provider._request = AsyncMock(return_value={"index_value": 12000.5, "index_change_percent": 1.1})

    data = await provider.get_index_data("TASI")

    assert data["index_name"] == "TASI"
    assert data["value"] == 12000.5
    provider._request.assert_awaited_once_with("/market/summary/", params={"index": "TASI"})


@pytest.mark.asyncio
async def test_get_index_data_accepts_nomu_and_nomuc():
    provider = _provider()
    provider._request = AsyncMock(return_value={"index_value": 100, "index_change_percent": 0})
    for name in ("NOMU", "NOMUC"):
        data = await provider.get_index_data(name)
        assert data["index_name"] == name


# --- get_market_news() : maps to /events/ ---------------------------------


@pytest.mark.asyncio
async def test_get_market_news_calls_events_endpoint():
    provider = _provider()
    provider._request = AsyncMock(return_value={"events": [{"headline": "x"}]})
    news = await provider.get_market_news(limit=5)
    assert news == [{"headline": "x"}]
    provider._request.assert_awaited_once_with("/events/", params={"limit": 5})


@pytest.mark.asyncio
async def test_get_market_news_surfaces_entitlement_error_not_swallowed():
    provider = _provider()
    provider._request = AsyncMock(side_effect=SahmkEntitlementError("Pro+ required"))
    with pytest.raises(SahmkEntitlementError):
        await provider.get_market_news()


# --- health_check() --------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_healthy_on_successful_call():
    provider = _provider()
    provider._request = AsyncMock(return_value={"index_value": 1, "index_change_percent": 0})
    assert await provider.health_check() == ProviderHealth.HEALTHY


@pytest.mark.asyncio
async def test_health_check_unhealthy_on_auth_failure():
    provider = _provider()
    provider._request = AsyncMock(side_effect=SahmkAuthenticationError("bad key"))
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


@pytest.mark.asyncio
async def test_health_check_degraded_on_other_errors():
    provider = _provider()
    provider._request = AsyncMock(side_effect=RuntimeError("network down"))
    assert await provider.health_check() == ProviderHealth.DEGRADED


# --- disconnect() ------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_closes_session_and_resets_state():
    provider = _provider()
    fake_session = MagicMock()
    fake_session.close = AsyncMock()
    provider.session = fake_session
    provider.authenticated = True

    await provider.disconnect()

    fake_session.close.assert_awaited_once()
    assert provider.session is None
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_disconnect_logs_but_does_not_raise_when_session_close_fails():
    provider = _provider()
    fake_session = MagicMock()
    fake_session.close = AsyncMock(side_effect=RuntimeError("close failed"))
    provider.session = fake_session
    await provider.disconnect()  # must not raise


@pytest.mark.asyncio
async def test_disconnect_is_a_noop_when_no_session_was_ever_opened():
    provider = _provider()
    assert provider.session is None
    await provider.disconnect()  # must not raise
    assert provider.session is None


# --- factory / config wiring -----------------------------------------------


def test_sahmk_provider_is_registered_with_factory():
    provider = MarketDataProviderFactory.create("sahmk", "https://sahmk.example.invalid", "key")
    assert isinstance(provider, SahmkMarketDataProvider)


def test_provider_uses_config_defaults_when_no_args_given(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "env-key")
    monkeypatch.setenv("SAHMK_BASE_URL", "https://env.example.invalid")

    provider = SahmkMarketDataProvider()

    assert provider.api_key == "env-key"
    assert provider.api_endpoint == "https://env.example.invalid"


def test_provider_accepts_injected_cache_and_circuit_breaker():
    cache = TTLCache()
    provider = _provider(cache=cache)
    assert provider._cache is cache


def test_provider_starts_with_zero_usage_count():
    provider = _provider()
    assert provider.request_count == 0


# --- end-to-end against a minimal fake aiohttp session ----------------------


class _FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in: get() returns one
    pre-scripted _FakeResponse per call, consumed in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.closed = False

    def get(self, *args, **kwargs):
        return self._responses.pop(0)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_request_end_to_end_sends_x_api_key_header_and_no_auth_endpoint(monkeypatch):
    captured = {}

    class _CapturingSession(_FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            return super().get()

    provider = _provider()
    provider.session = _CapturingSession([_FakeResponse(200, {"symbol": "1010", "price": 1})])

    await provider._request("/quote/1010/")

    assert captured["headers"] == {"X-API-Key": "key"}
    assert captured["url"] == "https://sahmk.example.invalid/quote/1010/"
    assert provider.request_count == 1


@pytest.mark.asyncio
async def test_request_end_to_end_401_raises_authentication_error():
    provider = _provider()
    provider.session = _FakeSession([_FakeResponse(401, {})])
    with pytest.raises(SahmkAuthenticationError):
        await provider._request("/quote/1010/")


@pytest.mark.asyncio
async def test_request_end_to_end_403_raises_entitlement_error():
    provider = _provider()
    provider.session = _FakeSession([_FakeResponse(403, {"error": "PLAN_LIMIT"})])
    with pytest.raises(SahmkEntitlementError):
        await provider._request("/events/")


@pytest.mark.asyncio
async def test_request_end_to_end_429_retries_and_eventually_succeeds(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    provider = _provider()
    provider.session = _FakeSession(
        [
            _FakeResponse(429, {}, headers={"Retry-After": "1"}),
            _FakeResponse(200, {"symbol": "1010", "price": 1}),
        ]
    )

    data = await provider._request("/quote/1010/")

    assert data == {"symbol": "1010", "price": 1}


@pytest.mark.asyncio
async def test_request_end_to_end_exhausts_retries_on_persistent_500(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    provider = _provider()
    provider.session = _FakeSession([_FakeResponse(500, {})] * 3)

    with pytest.raises(Exception):
        await provider._request("/quote/1010/")


@pytest.mark.asyncio
async def test_sahmk_rate_limited_error_carries_retry_after():
    err = _SahmkRateLimitedError("/quote/1010/", "3")
    assert err.retry_after == "3"


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_unexpected_exception():
    provider = _provider()
    provider._request = AsyncMock(side_effect=RuntimeError("unexpected"))
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


def test_sahmk_wait_falls_back_to_exponential_on_unparseable_retry_after():
    from src.market_data.providers.sahmk_market_data_provider import _sahmk_wait

    class _FakeOutcome:
        def exception(self):
            return _SahmkRateLimitedError("/quote/1010/", "not-a-number")

    class _FakeRetryState:
        outcome = _FakeOutcome()
        attempt_number = 1

    wait_seconds = _sahmk_wait(_FakeRetryState())
    assert isinstance(wait_seconds, float)


@pytest.mark.asyncio
async def test_request_raises_authentication_error_when_no_api_key_configured():
    provider = _provider(api_key="")
    with pytest.raises(SahmkAuthenticationError):
        await provider._request("/quote/1010/")


@pytest.mark.asyncio
async def test_request_lazily_creates_session_when_none_exists():
    provider = _provider()
    assert provider.session is None

    async def _fake_aiohttp_session():
        return _FakeSession([_FakeResponse(200, {"symbol": "1010", "price": 1})])

    # Patch aiohttp.ClientSession itself so _request's lazy
    # `self.session = aiohttp.ClientSession()` creates our fake instead
    # of a real one, without ever touching a real socket.
    import src.market_data.providers.sahmk_market_data_provider as mod

    fake_session = _FakeSession([_FakeResponse(200, {"symbol": "1010", "price": 1})])
    mod.aiohttp.ClientSession = lambda: fake_session
    try:
        data = await provider._request("/quote/1010/")
    finally:
        import aiohttp as real_aiohttp

        mod.aiohttp.ClientSession = real_aiohttp.ClientSession

    assert data == {"symbol": "1010", "price": 1}
    assert provider.session is fake_session


@pytest.mark.asyncio
async def test_request_raises_response_validation_error_on_non_json_200():
    class _BrokenJSONResponse(_FakeResponse):
        async def json(self):
            raise ValueError("not json")

    provider = _provider()
    provider.session = _FakeSession([_BrokenJSONResponse(200, None)])
    with pytest.raises(SahmkResponseValidationError):
        await provider._request("/quote/1010/")


@pytest.mark.asyncio
async def test_request_raises_request_error_on_unexpected_status_code():
    provider = _provider()
    provider.session = _FakeSession([_FakeResponse(418, {})])
    from src.market_data.providers.sahmk_market_data_provider import SahmkRequestError

    with pytest.raises(SahmkRequestError):
        await provider._request("/quote/1010/")
