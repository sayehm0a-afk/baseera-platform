"""Unit tests for src.market_intelligence.preflight -- the hard
"prove real data before scanning" gate strict real-data mode requires.
SahmkMarketDataProvider is replaced with a fake, matching
tests/unit/market_data/test_provider_factory.py's pattern, so no
network call is ever made.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.market_data import provider_factory
from src.market_intelligence.preflight import DATA_SOURCE_SAHMK_REAL, run_sahmk_preflight

_SECRET_MARKER = "shmk_live_do_not_leak_9f8e7d6c"


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


class _FakeSahmkProvider:
    is_synthetic = False

    def __init__(self, *args, **kwargs):
        self.disconnected = False

    async def authenticate(self):
        return True

    async def disconnect(self):
        self.disconnected = True

    async def get_latest_quote(self, symbol):
        return {"price": 42.5, "timestamp": "2026-08-03T10:00:00+03:00"}

    async def get_stock_data(self, symbol):
        return {"close": 42.5, "date": "2026-08-03"}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    monkeypatch.setattr(provider_factory, "SahmkMarketDataProvider", _FakeSahmkProvider)
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    monkeypatch.delenv("STRICT_REAL_DATA", raising=False)
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60")
    yield
    provider_factory.reset_provider_cache()


@pytest.mark.asyncio
async def test_not_ready_when_strict_mode_is_off(factory):
    result = await run_sahmk_preflight(factory)
    assert result.ready is False
    assert result.strict_real_data is False
    assert "STRICT_REAL_DATA" in result.reason


@pytest.mark.asyncio
async def test_not_ready_when_key_is_missing(factory, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    result = await run_sahmk_preflight(factory)
    assert result.ready is False
    assert "SAHMK_API_KEY" in result.reason


@pytest.mark.asyncio
async def test_ready_true_with_real_authenticated_data(factory, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    result = await run_sahmk_preflight(factory)

    assert result.ready is True
    assert result.provider == "sahmk"
    assert result.authenticated is True
    assert result.strict_real_data is True
    assert result.synthetic_allowed is False
    assert result.connectivity == "SUCCESS"
    assert result.database_ok is True
    assert result.sample_symbol is not None
    assert result.sample_timestamp is not None
    assert result.data_source == DATA_SOURCE_SAHMK_REAL


@pytest.mark.asyncio
async def test_not_ready_when_sample_quote_request_fails(factory, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _broken_quote(self, symbol):
        raise RuntimeError("simulated SAHMK error")

    _FakeSahmkProvider.get_latest_quote = _broken_quote
    _FakeSahmkProvider.get_stock_data = _broken_quote

    result = await run_sahmk_preflight(factory)
    assert result.ready is False
    assert result.authenticated is True
    assert result.connectivity == "FAILED"


@pytest.mark.asyncio
async def test_to_dict_and_reason_never_contain_the_api_key(factory, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _rejected(self):
        return False

    _FakeSahmkProvider.authenticate = _rejected

    result = await run_sahmk_preflight(factory)
    assert result.ready is False
    payload = str(result.to_dict())
    assert _SECRET_MARKER not in payload
