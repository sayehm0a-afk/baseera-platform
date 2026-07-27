"""Unit tests for MarketScanner."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.market_intelligence.scanner import MarketScanner
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


def _add_stock_with_bars(factory, symbol, sector="Energy", count=60):
    session = factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    for i in range(count):
        price += 0.08
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(price)), high=Decimal(str(price + 0.5)), low=Decimal(str(price - 0.5)),
                close=Decimal(str(price)), volume=1000 + i,
            )
        )
    session.commit()
    session.close()


@pytest.mark.asyncio
async def test_scan_produces_a_successful_outcome_with_snapshots(factory):
    _add_stock_with_bars(factory, "2222")
    scanner = MarketScanner(session_factory=factory, market_provider=DevMarketDataProvider())

    outcomes = await scanner.scan(["2222"])

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.success is True
    assert outcome.sector == "Energy"
    assert outcome.report is not None
    assert outcome.recommendation is not None
    assert outcome.technical_snapshot is not None
    assert outcome.latest_price is not None


@pytest.mark.asyncio
async def test_scan_skips_unregistered_symbol(factory):
    scanner = MarketScanner(session_factory=factory, market_provider=DevMarketDataProvider())

    outcomes = await scanner.scan(["9999"])

    assert outcomes[0].success is False
    assert outcomes[0].skipped_reason == "stock_not_registered"
    assert outcomes[0].error is None


@pytest.mark.asyncio
async def test_scan_skips_symbol_with_no_ingested_data(factory):
    session = factory()
    session.add(Stock(symbol="2222", name_en="Stock 2222", sector="Energy"))
    session.commit()
    session.close()

    scanner = MarketScanner(session_factory=factory, market_provider=DevMarketDataProvider())
    outcomes = await scanner.scan(["2222"])

    assert outcomes[0].success is False
    assert outcomes[0].skipped_reason == "insufficient_data"


@pytest.mark.asyncio
async def test_scan_handles_multiple_symbols_independently(factory):
    _add_stock_with_bars(factory, "1010", sector="Banks")
    _add_stock_with_bars(factory, "2222", sector="Energy")
    scanner = MarketScanner(session_factory=factory, market_provider=DevMarketDataProvider())

    outcomes = await scanner.scan(["1010", "2222", "9999"])

    by_symbol = {o.symbol: o for o in outcomes}
    assert by_symbol["1010"].success is True
    assert by_symbol["2222"].success is True
    assert by_symbol["9999"].skipped_reason == "stock_not_registered"


@pytest.mark.asyncio
async def test_scan_retries_a_transient_failure_and_eventually_succeeds(factory, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("MARKET_SCAN_RETRY_BASE_DELAY_SECONDS", "0.001")
    _add_stock_with_bars(factory, "2222")

    scanner = MarketScanner(session_factory=factory, market_provider=DevMarketDataProvider())

    calls = {"n": 0}
    real_scan_one = scanner._scan_one

    async def _flaky_scan_one(symbol):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient failure")
        return await real_scan_one(symbol)

    scanner._scan_one = _flaky_scan_one

    outcomes = await scanner.scan(["2222"])

    assert outcomes[0].success is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_scan_records_failure_after_exhausting_retries(factory, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("MARKET_SCAN_RETRY_BASE_DELAY_SECONDS", "0.001")
    scanner = MarketScanner(session_factory=factory, market_provider=DevMarketDataProvider())

    async def _always_fails(symbol):
        raise RuntimeError("permanent failure")

    scanner._scan_one = _always_fails

    outcomes = await scanner.scan(["2222"])

    assert outcomes[0].success is False
    assert outcomes[0].error is not None
    assert "permanent failure" in outcomes[0].error


def test_summarize_counts_success_skip_and_failure():
    from tests.unit.market_intelligence._fixtures import make_outcome

    outcomes = [
        make_outcome(symbol="A", success=True),
        make_outcome(symbol="B", success=False, report=None, skipped_reason="insufficient_data"),
        make_outcome(symbol="C", success=False, report=None, error="boom"),
    ]
    started_at = datetime.now(timezone.utc)

    summary = MarketScanner.summarize(outcomes, started_at)

    assert summary.total_requested == 3
    assert summary.total_succeeded == 1
    assert summary.total_skipped == 1
    assert summary.total_failed == 1
