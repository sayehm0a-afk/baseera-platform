"""Unit tests for SahmakMarketDataProvider (M2.13).

No real Sahmak endpoint exists or is contracted -- every test either
mocks this class's own `_request`/`session` boundary directly (never
reaching a real network) or exercises the credential-missing path,
which by design never opens a socket at all.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.providers.market_data_provider import (
    MarketDataProviderFactory,
    ProviderHealth,
)
from src.market_data.providers.sahmak_market_data_provider import (
    SahmakAuthenticationError,
    SahmakMarketDataProvider,
)
from src.market_data.validators.symbol_validator import InvalidSymbolError


def _provider(**kwargs):
    defaults = dict(api_endpoint="https://sahmak.example.invalid", api_key="key", api_secret="secret")
    defaults.update(kwargs)
    return SahmakMarketDataProvider(**defaults)


@pytest.mark.asyncio
async def test_authenticate_fails_fast_when_credentials_missing():
    provider = SahmakMarketDataProvider(api_endpoint="", api_key="", api_secret="")
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_succeeds_and_stores_token():
    provider = _provider()
    provider._circuit_breaker.execute = AsyncMock(return_value={"token": "abc123"})
    result = await provider.authenticate()
    assert result is True
    assert provider.authenticated is True
    assert provider.auth_token == "abc123"


@pytest.mark.asyncio
async def test_authenticate_returns_false_when_circuit_breaker_open():
    provider = _provider()
    provider._circuit_breaker.execute = AsyncMock(side_effect=CircuitBreakerOpenError())
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_get_stock_data_rejects_malformed_symbol_before_any_request():
    provider = _provider()
    provider._request = AsyncMock()
    with pytest.raises(InvalidSymbolError):
        await provider.get_stock_data("AAPL")
    provider._request.assert_not_called()


@pytest.mark.asyncio
async def test_get_stock_data_calls_request_and_caches_result():
    provider = _provider()
    provider.authenticated = True
    provider._request = AsyncMock(return_value={"symbol": "1010", "close": 42})

    first = await provider.get_stock_data("1010")
    second = await provider.get_stock_data("1010")

    assert first == {"symbol": "1010", "close": 42}
    assert second == {"symbol": "1010", "close": 42}
    provider._request.assert_awaited_once()  # second call was a cache hit


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
async def test_get_historical_ohlcv_returns_bars_from_request():
    provider = _provider()
    provider._request = AsyncMock(
        return_value={"bars": [{"symbol": "1010", "close": 10, "timestamp": "2024-01-01T00:00:00+00:00"}]}
    )
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    bars = await provider.get_historical_ohlcv("1010", start, end)

    assert len(bars) == 1
    assert bars[0]["symbol"] == "1010"


@pytest.mark.asyncio
async def test_request_raises_when_not_authenticated():
    provider = _provider()
    provider.authenticated = False
    with pytest.raises(SahmakAuthenticationError):
        await provider._request("/stocks/data")


@pytest.mark.asyncio
async def test_health_check_returns_unhealthy_on_request_failure():
    provider = _provider()
    provider._request = AsyncMock(side_effect=RuntimeError("network down"))
    status = await provider.health_check()
    assert status == ProviderHealth.UNHEALTHY


@pytest.mark.asyncio
async def test_health_check_reflects_reported_status():
    provider = _provider()
    provider._request = AsyncMock(return_value={"status": "healthy"})
    status = await provider.health_check()
    assert status == ProviderHealth.HEALTHY


@pytest.mark.asyncio
async def test_disconnect_closes_session_and_resets_state():
    provider = _provider()
    fake_session = MagicMock()
    fake_session.close = AsyncMock()
    provider.session = fake_session
    provider.authenticated = True
    provider.auth_token = "abc"

    await provider.disconnect()

    fake_session.close.assert_awaited_once()
    assert provider.session is None
    assert provider.authenticated is False
    assert provider.auth_token is None


def test_sahmak_provider_is_registered_with_factory():
    provider = MarketDataProviderFactory.create(
        "sahmak", "https://sahmak.example.invalid", "key", api_secret="secret"
    )
    assert isinstance(provider, SahmakMarketDataProvider)


def test_provider_uses_config_defaults_when_no_args_given(monkeypatch):
    monkeypatch.setenv("SAHMAK_API_KEY", "env-key")
    monkeypatch.setenv("SAHMAK_API_SECRET", "env-secret")
    monkeypatch.setenv("SAHMAK_BASE_URL", "https://env.example.invalid")

    provider = SahmakMarketDataProvider()

    assert provider.api_key == "env-key"
    assert provider.api_secret == "env-secret"
    assert provider.api_endpoint == "https://env.example.invalid"


def test_provider_accepts_injected_cache_and_circuit_breaker():
    cache = TTLCache()
    provider = _provider(cache=cache)
    assert provider._cache is cache


@pytest.mark.asyncio
async def test_get_index_data_calls_request():
    provider = _provider()
    provider._request = AsyncMock(return_value={"index_name": "TASI", "value": 11000})
    data = await provider.get_index_data("TASI")
    assert data["index_name"] == "TASI"
    provider._request.assert_awaited_once_with("/indices/data", params={"index": "TASI"})


@pytest.mark.asyncio
async def test_get_market_news_calls_request_and_unwraps_news_key():
    provider = _provider()
    provider._request = AsyncMock(return_value={"news": [{"headline": "x"}]})
    news = await provider.get_market_news(limit=5)
    assert news == [{"headline": "x"}]
    provider._request.assert_awaited_once_with("/news/market", params={"limit": 5})


@pytest.mark.asyncio
async def test_get_market_news_returns_empty_list_when_no_news_key():
    provider = _provider()
    provider._request = AsyncMock(return_value={})
    assert await provider.get_market_news() == []


@pytest.mark.asyncio
async def test_health_check_reflects_degraded_status():
    provider = _provider()
    provider._request = AsyncMock(return_value={"status": "degraded"})
    assert await provider.health_check() == ProviderHealth.DEGRADED


@pytest.mark.asyncio
async def test_health_check_reflects_unrecognized_status_as_unhealthy():
    provider = _provider()
    provider._request = AsyncMock(return_value={"status": "something-else"})
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


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


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in: post()/request() both
    return one pre-scripted _FakeResponse per call, consumed in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.closed = False

    def post(self, *args, **kwargs):
        return self._responses.pop(0)

    def request(self, *args, **kwargs):
        return self._responses.pop(0)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_authenticate_end_to_end_against_fake_session():
    provider = _provider()
    provider.session = _FakeSession([_FakeResponse(200, {"token": "real-token"})])

    result = await provider.authenticate()

    assert result is True
    assert provider.auth_token == "real-token"
    assert provider.authenticated is True


@pytest.mark.asyncio
async def test_authenticate_end_to_end_non_200_response_is_treated_as_failure(monkeypatch):
    # tenacity's wait_exponential otherwise sleeps for real between the
    # 3 configured attempts -- patched to instant so this test doesn't
    # take ~6s asserting an error path that's expected to exhaust retries.
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    provider = _provider()
    # Every retry attempt gets a fresh 500 response.
    provider.session = _FakeSession([_FakeResponse(500, {})] * 3)

    result = await provider.authenticate()

    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_request_end_to_end_against_fake_session():
    provider = _provider()
    provider.authenticated = True
    provider.auth_token = "tok"
    provider.session = _FakeSession([_FakeResponse(200, {"symbol": "1010", "close": 5})])

    data = await provider._request("/stocks/data", params={"symbol": "1010"})

    assert data == {"symbol": "1010", "close": 5}


@pytest.mark.asyncio
async def test_request_re_authenticates_and_retries_on_401(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    provider = _provider()
    provider.authenticated = True
    provider.auth_token = "stale-token"
    # First _request attempt: 401 -> triggers authenticate() (consumes the
    # /auth/token response) -> tenacity retries _do_request -> 200.
    provider.session = _FakeSession(
        [
            _FakeResponse(401, {}),
            _FakeResponse(200, {"token": "fresh-token"}),
            _FakeResponse(200, {"symbol": "1010", "close": 5}),
        ]
    )

    data = await provider._request("/stocks/data", params={"symbol": "1010"})

    assert data == {"symbol": "1010", "close": 5}
    assert provider.auth_token == "fresh-token"


@pytest.mark.asyncio
async def test_request_raises_on_unexpected_status(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    provider = _provider()
    provider.authenticated = True
    provider.auth_token = "tok"
    provider.session = _FakeSession([_FakeResponse(500, {})] * 3)

    with pytest.raises(Exception):
        await provider._request("/stocks/data")
