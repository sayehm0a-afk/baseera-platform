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
async def test_refreshes_name_ar_via_company_profile(session_factory):
    """Phase 2H: name_ar was previously never written by ingestion at
    all (a structural gap affecting every symbol, including 2222) --
    once the provider supplies a real Arabic name, _apply_entry must
    persist it."""
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_company_profile = AsyncMock(
        return_value={"symbol": "2222", "name": "Saudi Aramco", "name_ar": "أرامكو السعودية"}
    )

    result = await sync_symbols(["2222"], provider, session_factory)
    assert result.rows_upserted == 1

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    assert stock.name_ar == "أرامكو السعودية"
    session.close()


@pytest.mark.asyncio
async def test_missing_name_ar_leaves_it_null_rather_than_fabricating(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_company_profile = AsyncMock(
        return_value={"symbol": "2222", "name": "Saudi Aramco"}  # no name_ar key at all
    )

    await sync_symbols(["2222"], provider, session_factory)

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    assert stock.name_ar is None
    session.close()


@pytest.mark.asyncio
async def test_refreshes_industry_and_exchange_via_company_profile(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_company_profile = AsyncMock(
        return_value={
            "symbol": "2222", "name": "Saudi Aramco", "sector": "Energy",
            "industry": "Oil & Gas", "exchange": "Tadawul",
        }
    )

    result = await sync_symbols(["2222"], provider, session_factory)
    assert result.rows_upserted == 1

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    assert stock.industry == "Oil & Gas"
    assert stock.exchange == "Tadawul"
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
async def test_discover_all_deactivates_a_non_eligible_instrument(session_factory):
    """A discovered ETF/REIT/sukuk (universe_policy classified
    is_eligible=False on the directory entry) must be persisted with
    is_active=False, so SymbolSelector (which filters Stock.is_active)
    never scans it as if it were a common stock -- while still creating
    a Stock row, for admin/coverage visibility."""
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_symbol_directory = AsyncMock(
        return_value=[
            {
                "symbol": "2222", "name": "Saudi Aramco", "sector": "Energy",
                "is_eligible": True, "instrument_bucket": "MAIN_MARKET_EQUITY", "exclusion_reason": None,
            },
            {
                "symbol": "4342", "name": "Some REIT Fund",
                "is_eligible": False, "instrument_bucket": "REIT", "exclusion_reason": "security_type='REIT'",
            },
        ]
    )

    result = await sync_symbols([], provider, session_factory, discover_all=True)
    assert result.symbols_succeeded == 2

    session = session_factory()
    stock_2222 = session.query(Stock).filter_by(symbol="2222").one()
    assert stock_2222.is_active is True
    assert stock_2222.instrument_bucket == "MAIN_MARKET_EQUITY"

    stock_4342 = session.query(Stock).filter_by(symbol="4342").one()
    assert stock_4342.is_active is False
    assert stock_4342.instrument_bucket == "REIT"
    assert stock_4342.exclusion_reason == "security_type='REIT'"
    session.close()


@pytest.mark.asyncio
async def test_missing_is_eligible_key_leaves_is_active_at_its_default(session_factory):
    """A get_company_profile() single-symbol lookup (no is_eligible key
    at all) must not touch is_active -- only directory entries that
    actually ran through universe_policy carry that key."""
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_company_profile = AsyncMock(return_value={"name": "Saudi Aramco"})

    result = await sync_symbols(["2222"], provider, session_factory)
    assert result.rows_upserted == 1  # name changed, but not because of is_active

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="2222").one().is_active is True
    session.close()


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
