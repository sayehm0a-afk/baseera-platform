"""Unit tests for ingest_historical_ohlcv -- in-memory SQLite, no live
DB/network. Mirrors test_ingest_ohlcv.py's fixtures/conventions."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock
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
async def test_ingest_creates_stock_and_all_bars_in_range(session_factory):
    provider = DevMarketDataProvider()
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 5, tzinfo=timezone.utc)

    result = await ingest_historical_ohlcv(["1010"], start, end, provider, session_factory)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 0
    assert result.bars_upserted == 5
    assert result.success is True

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert session.query(PriceBar).filter_by(stock_id=stock.id).count() == 5
    session.close()


@pytest.mark.asyncio
async def test_ingest_multiple_symbols_sums_bars_upserted(session_factory):
    provider = DevMarketDataProvider()
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    result = await ingest_historical_ohlcv(["1010", "2222"], start, end, provider, session_factory)

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 2
    assert result.bars_upserted == 4

    session = session_factory()
    assert session.query(Stock).count() == 2
    assert session.query(PriceBar).count() == 4
    session.close()


@pytest.mark.asyncio
async def test_ingest_is_idempotent_upsert_not_duplicate(session_factory):
    provider = DevMarketDataProvider()
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)

    await ingest_historical_ohlcv(["1010"], start, end, provider, session_factory)
    await ingest_historical_ohlcv(["1010"], start, end, provider, session_factory)

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    assert session.query(PriceBar).count() == 3
    session.close()


@pytest.mark.asyncio
async def test_ingest_isolates_per_symbol_failures(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    good_bars = [
        {
            "symbol": "1010",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1000,
            "timestamp": "2026-01-05T10:00:00+00:00",
        }
    ]

    async def get_historical_ohlcv(symbol, start, end):
        if symbol == "BAD":
            raise RuntimeError("simulated provider failure")
        return good_bars

    provider.get_historical_ohlcv = AsyncMock(side_effect=get_historical_ohlcv)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    result = await ingest_historical_ohlcv(["1010", "BAD"], start, end, provider, session_factory)

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 1
    assert "BAD" in result.errors
    assert result.success is False

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    assert session.query(Stock).filter_by(symbol="BAD").count() == 0
    session.close()
