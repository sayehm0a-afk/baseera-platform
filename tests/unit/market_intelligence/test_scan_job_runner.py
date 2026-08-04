"""Unit tests for run_market_scan_job's strict real-data pre-flight
gate -- a full-market scan must not even begin under STRICT_REAL_DATA
unless a real, authenticated SAHMK request has just succeeded.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import MarketScanStatus, Stock
from src.market_data import provider_factory
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.services.scan_job_runner import run_market_scan_job


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    monkeypatch.delenv("STRICT_REAL_DATA", raising=False)
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60")
    yield
    provider_factory.reset_provider_cache()


def _seed_stock(factory, symbol="2222"):
    session = factory()
    session.add(Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy"))
    session.commit()
    session.close()


@pytest.mark.asyncio
async def test_strict_mode_blocks_the_scan_before_it_starts_when_key_is_missing(factory, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    _seed_stock(factory)
    repo = MarketIntelligenceRepository()
    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    await run_market_scan_job(run_id, factory, market_provider=object(), symbols=["2222"])

    session = factory()
    run_row = repo.get_run(session, run_id)
    assert run_row.status is MarketScanStatus.FAILED
    assert "preflight" in run_row.error_summary.lower()
    assert "SAHMK_API_KEY" in run_row.error_summary
    session.close()


@pytest.mark.asyncio
async def test_non_strict_mode_is_unaffected_by_the_preflight_gate(factory):
    """Regression guard: with STRICT_REAL_DATA unset, the scan proceeds
    exactly as before -- no pre-flight check runs at all."""
    _seed_stock(factory)
    repo = MarketIntelligenceRepository()
    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider

    await run_market_scan_job(run_id, factory, market_provider=DevMarketDataProvider(), symbols=["2222"])

    session = factory()
    run_row = repo.get_run(session, run_id)
    # Ran to completion (SUCCESS), not blocked by any preflight gate.
    assert run_row.status is MarketScanStatus.SUCCESS
    session.close()
