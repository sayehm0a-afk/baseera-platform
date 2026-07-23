"""Unit tests for ingest_ohlcv -- in-memory SQLite, no live DB/network."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.market_data.ingestion.ingest_ohlcv import ingest_ohlcv
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_ingest_creates_stock_and_price_bar(session_factory):
    provider = DevMarketDataProvider()

    result = await ingest_ohlcv(["1010"], provider, session_factory)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 0
    assert result.success is True

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert stock.name_en == "Stock 1010"
    bar = session.query(PriceBar).filter_by(stock_id=stock.id).one()
    assert bar.timeframe == Timeframe.ONE_DAY
    assert bar.open > 0
    session.close()


@pytest.mark.asyncio
async def test_ingest_multiple_symbols(session_factory):
    provider = DevMarketDataProvider()

    result = await ingest_ohlcv(["1010", "2222", "1120"], provider, session_factory)

    assert result.symbols_requested == 3
    assert result.symbols_succeeded == 3

    session = session_factory()
    assert session.query(Stock).count() == 3
    assert session.query(PriceBar).count() == 3
    session.close()


@pytest.mark.asyncio
async def test_ingest_reuses_existing_stock(session_factory):
    provider = DevMarketDataProvider()

    await ingest_ohlcv(["1010"], provider, session_factory)
    await ingest_ohlcv(["1010"], provider, session_factory)

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    # Same synthetic day -> same PriceBar identity -> upsert, not a second row
    assert session.query(PriceBar).count() == 1
    session.close()


@pytest.mark.asyncio
async def test_ingest_isolates_per_symbol_failures(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    good_data = {
        "symbol": "1010",
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 1000,
        "timestamp": "2026-01-05T10:00:00+00:00",
    }

    async def get_stock_data(symbol):
        if symbol == "BAD":
            raise RuntimeError("simulated provider failure")
        return good_data

    provider.get_stock_data = AsyncMock(side_effect=get_stock_data)

    result = await ingest_ohlcv(["1010", "BAD"], provider, session_factory)

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 1
    assert "BAD" in result.errors
    assert result.success is False

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    assert session.query(Stock).filter_by(symbol="BAD").count() == 0
    session.close()
