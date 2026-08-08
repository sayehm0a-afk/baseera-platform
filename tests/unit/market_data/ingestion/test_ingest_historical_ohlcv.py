"""Unit tests for ingest_historical_ohlcv -- in-memory SQLite, no live
DB/network."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.market_data.ingestion.ingest_historical_ohlcv import ingest_historical_ohlcv
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_backfills_new_symbol(session_factory):
    provider = DevMarketDataProvider()

    result = await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=10)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 11  # inclusive of both endpoints: today - 10 .. today

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert session.query(PriceBar).filter_by(stock_id=stock.id).count() == 11
    session.close()


@pytest.mark.asyncio
async def test_incremental_catch_up_only_fetches_the_gap(session_factory):
    provider = DevMarketDataProvider()

    # First backfill: 10 days.
    await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=10)
    # Second run: already have every bar through today -- nothing new to fetch.
    result = await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=10)

    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 0

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert session.query(PriceBar).filter_by(stock_id=stock.id).count() == 11  # unchanged
    session.close()


@pytest.mark.asyncio
async def test_incremental_catch_up_fetches_only_missing_days(session_factory):
    session = session_factory()
    stock = Stock(symbol="1010", name_en="Stock 1010")
    session.add(stock)
    session.commit()
    today = datetime.now(timezone.utc).date()
    stale_day = today - timedelta(days=5)
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=datetime(stale_day.year, stale_day.month, stale_day.day, tzinfo=timezone.utc),
            open=Decimal("10"), high=Decimal("11"), low=Decimal("9"), close=Decimal("10.5"),
            volume=1000,
        )
    )
    session.commit()
    session.close()

    provider = DevMarketDataProvider()
    result = await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=90)

    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 5  # stale_day+1 .. today, inclusive

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert session.query(PriceBar).filter_by(stock_id=stock.id).count() == 6  # 1 pre-existing + 5 new
    session.close()


@pytest.mark.asyncio
async def test_is_idempotent_no_duplicate_rows_on_rerun(session_factory):
    provider = DevMarketDataProvider()
    await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=5)
    await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=5)

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert session.query(PriceBar).filter_by(stock_id=stock.id).count() == 6
    session.close()


@pytest.mark.asyncio
async def test_isolates_per_symbol_failures(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    good_bar = {
        "symbol": "1010", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
        "volume": 1000, "timestamp": "2026-01-05T00:00:00+00:00",
    }

    async def get_historical_ohlcv(symbol, start, end, interval="1d"):
        if symbol == "BAD":
            raise RuntimeError("simulated provider failure")
        return [good_bar]

    provider.get_historical_ohlcv = AsyncMock(side_effect=get_historical_ohlcv)

    result = await ingest_historical_ohlcv(["1010", "BAD"], provider, session_factory)

    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 1
    assert "BAD" in result.errors

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    assert session.query(Stock).filter_by(symbol="BAD").count() == 0
    session.close()


@pytest.mark.asyncio
async def test_empty_symbol_list_succeeds_trivially(session_factory):
    provider = DevMarketDataProvider()
    result = await ingest_historical_ohlcv([], provider, session_factory)
    assert result.symbols_requested == 0
    assert result.symbols_failed == 0


@pytest.mark.asyncio
async def test_records_zero_progress_reason_for_a_new_symbol_with_no_bars(session_factory):
    """Root-cause regression for the real production gap (408/408
    ingestion jobs reported 'success' but only 393 symbols had any
    PriceBar rows): a provider call that succeeds (no exception) but
    returns zero bars for a genuinely new symbol must be recorded by
    reason, not silently folded into a bare 'success' count."""
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_historical_ohlcv = AsyncMock(return_value=[])

    result = await ingest_historical_ohlcv(["9999"], provider, session_factory)

    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 0
    assert "9999" in result.zero_progress
    assert "zero total price bars" in result.zero_progress["9999"]


@pytest.mark.asyncio
async def test_no_zero_progress_reason_when_bars_are_returned(session_factory):
    provider = DevMarketDataProvider()
    result = await ingest_historical_ohlcv(["1010"], provider, session_factory, backfill_days=5)
    assert result.zero_progress == {}


@pytest.mark.asyncio
async def test_no_zero_progress_reason_for_an_already_caught_up_symbol(session_factory):
    """A symbol with existing bars whose incremental catch-up window is
    empty (already up to date) is a legitimate, uninteresting no-op --
    must not be reported as a zero-progress gap."""
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_historical_ohlcv = AsyncMock(return_value=[])

    session = session_factory()
    stock = Stock(symbol="2222", name_en="Saudi Aramco")
    session.add(stock)
    session.flush()
    session.add(
        PriceBar(
            stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
            timestamp=datetime.now(timezone.utc), open=Decimal("10"), high=Decimal("10"),
            low=Decimal("10"), close=Decimal("10"), volume=100, source="sahmk", is_synthetic=False,
        )
    )
    session.commit()
    session.close()

    result = await ingest_historical_ohlcv(["2222"], provider, session_factory)
    assert result.zero_progress == {}
