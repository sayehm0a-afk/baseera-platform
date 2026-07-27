"""Unit tests for ingest_symbols.sync_symbols -- in-memory SQLite, no
live DB/network."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import Stock
from src.market_data.ingestion.ingest_symbols import sync_symbols
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_creates_placeholder_stocks_when_provider_has_no_profile_support(session_factory):
    """DevMarketDataProvider has no get_company_profile() -- symbols
    must still be created (with the get_or_create_stock placeholder
    name), just without a metadata refresh."""
    provider = DevMarketDataProvider()
    result = await sync_symbols(["1010", "2222"], provider, session_factory)

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 2

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").one().name_en == "Stock 1010"
    session.close()


@pytest.mark.asyncio
async def test_refreshes_name_and_sector_via_company_profile(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_company_profile = AsyncMock(
        return_value={"symbol": "2222", "name": "Saudi Aramco", "sector": "Energy"}
    )

    result = await sync_symbols(["2222"], provider, session_factory)
    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 1  # name_en/sector actually changed

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    assert stock.name_en == "Saudi Aramco"
    assert stock.sector == "Energy"
    session.close()


@pytest.mark.asyncio
async def test_no_op_refresh_does_not_count_as_a_row_upserted(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_company_profile = AsyncMock(return_value={})  # no name/sector at all

    result = await sync_symbols(["2222"], provider, session_factory)
    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_discover_all_registers_symbols_beyond_the_explicit_list(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_symbol_directory = AsyncMock(
        return_value=[
            {"symbol": "2222", "name": "Saudi Aramco", "sector": "Energy"},
            {"symbol": "1120", "name": "Al Rajhi Bank", "sector": "Financials"},
        ]
    )

    result = await sync_symbols([], provider, session_factory, discover_all=True)

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 2
    assert result.rows_upserted == 2
    provider.get_symbol_directory.assert_awaited_once()

    session = session_factory()
    assert {s.symbol for s in session.query(Stock).all()} == {"2222", "1120"}
    assert session.query(Stock).filter_by(symbol="2222").one().sector == "Energy"
    session.close()


@pytest.mark.asyncio
async def test_discover_all_does_not_duplicate_an_already_explicit_symbol(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_symbol_directory = AsyncMock(
        return_value=[{"symbol": "2222", "name": "Saudi Aramco", "sector": "Energy"}]
    )

    result = await sync_symbols(["2222"], provider, session_factory, discover_all=True)
    assert result.symbols_requested == 1  # deduped, not 2

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="2222").count() == 1
    session.close()


@pytest.mark.asyncio
async def test_discover_all_skipped_gracefully_when_provider_lacks_directory_support(
    session_factory,
):
    """DevMarketDataProvider has no get_symbol_directory() -- must not
    raise, just sync the explicitly configured symbols."""
    provider = DevMarketDataProvider()
    result = await sync_symbols(["1010"], provider, session_factory, discover_all=True)
    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1


@pytest.mark.asyncio
async def test_directory_discovery_failure_falls_back_to_explicit_symbols_only(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_symbol_directory = AsyncMock(side_effect=RuntimeError("SAHMK unreachable"))
    provider.get_company_profile = AsyncMock(return_value={"name": "Stock 1010"})

    result = await sync_symbols(["1010"], provider, session_factory, discover_all=True)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 0


@pytest.mark.asyncio
async def test_isolates_per_symbol_failures(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    async def get_company_profile(symbol):
        if symbol == "BAD":
            raise RuntimeError("simulated provider failure")
        return {"name": "Good Co"}

    provider.get_company_profile = AsyncMock(side_effect=get_company_profile)

    result = await sync_symbols(["1010", "BAD"], provider, session_factory)

    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 1
    assert "BAD" in result.errors

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    assert session.query(Stock).filter_by(symbol="BAD").count() == 0
    session.close()
