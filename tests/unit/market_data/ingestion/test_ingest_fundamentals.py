"""Unit tests for ingest_fundamentals -- in-memory SQLite, no live
DB/network."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import FundamentalSnapshot, PeriodType, Stock
from src.market_data.ingestion.ingest_fundamentals import ingest_fundamentals
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_ingest_creates_stock_and_fundamental_snapshot(session_factory):
    provider = DevFundamentalDataProvider()

    result = await ingest_fundamentals(["1010"], provider, session_factory)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 0
    assert result.success is True

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="1010").one()
    assert stock.name_en == "Stock 1010"
    snapshot = session.query(FundamentalSnapshot).filter_by(stock_id=stock.id).one()
    assert snapshot.period_type == PeriodType.ANNUAL
    assert snapshot.revenue > 0
    assert snapshot.is_synthetic is True
    session.close()


@pytest.mark.asyncio
async def test_ingest_multiple_symbols(session_factory):
    provider = DevFundamentalDataProvider()

    result = await ingest_fundamentals(["1010", "2222", "1120"], provider, session_factory)

    assert result.symbols_requested == 3
    assert result.symbols_succeeded == 3

    session = session_factory()
    assert session.query(Stock).count() == 3
    assert session.query(FundamentalSnapshot).count() == 3
    session.close()


@pytest.mark.asyncio
async def test_ingest_reuses_existing_stock_and_upserts_snapshot(session_factory):
    provider = DevFundamentalDataProvider()

    await ingest_fundamentals(["1010"], provider, session_factory)
    await ingest_fundamentals(["1010"], provider, session_factory)

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    # Same synthetic fiscal period -> same snapshot identity -> upsert,
    # not a second row.
    assert session.query(FundamentalSnapshot).count() == 1
    session.close()


@pytest.mark.asyncio
async def test_ingest_respects_period_type(session_factory):
    provider = DevFundamentalDataProvider()

    await ingest_fundamentals(["1010"], provider, session_factory, period_type="annual")
    await ingest_fundamentals(["1010"], provider, session_factory, period_type="quarterly")

    session = session_factory()
    assert session.query(FundamentalSnapshot).filter_by(period_type=PeriodType.ANNUAL).count() == 1
    assert session.query(FundamentalSnapshot).filter_by(period_type=PeriodType.QUARTERLY).count() == 1
    session.close()


@pytest.mark.asyncio
async def test_ingest_persists_a_snapshot_when_sahmk_never_reports_current_assets_shares_eps(
    session_factory,
):
    # Real SAHMK /financials/ shape (confirmed live, workflow run
    # 30436660246): current_assets/current_liabilities/
    # shares_outstanding/eps are absent, not present-but-null.
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_fundamentals = AsyncMock(
        return_value={
            "symbol": "1120",
            "period_type": "annual",
            "fiscal_period_end": "2025-12-31",
            "revenue": 39_093_965_000,
            "gross_profit": 6_730_335,
            "net_income": 24_791_754_000,
            "total_assets": 1_043_268_297_000,
            "total_liabilities": 900_355_952_000,
            "total_equity": 142_912_345_000,
            "total_debt": 80_320_898_000,
            "dividend_per_share": 0,
            "source": "sahmk",
            "is_synthetic": False,
        }
    )

    result = await ingest_fundamentals(["1120"], provider, session_factory)

    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 0

    session = session_factory()
    snapshot = session.query(FundamentalSnapshot).filter_by(stock_id=session.query(Stock).one().id).one()
    assert snapshot.revenue == 39_093_965_000
    assert snapshot.current_assets is None
    assert snapshot.current_liabilities is None
    assert snapshot.shares_outstanding is None
    assert snapshot.eps is None
    session.close()


@pytest.mark.asyncio
async def test_ingest_isolates_per_symbol_failures(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    good_data = {
        "symbol": "1010",
        "period_type": "annual",
        "fiscal_period_end": "2025-12-31",
        "revenue": 1_000_000_000,
        "gross_profit": 400_000_000,
        "net_income": 150_000_000,
        "total_assets": 3_000_000_000,
        "total_liabilities": 1_200_000_000,
        "total_equity": 1_800_000_000,
        "current_assets": 700_000_000,
        "current_liabilities": 400_000_000,
        "inventory": 100_000_000,
        "cash_and_equivalents": 200_000_000,
        "total_debt": 500_000_000,
        "shares_outstanding": 500_000_000,
        "eps": 0.3,
        "dividend_per_share": 0.1,
        "source": "dev-synthetic",
        "is_synthetic": True,
    }

    async def get_fundamentals(symbol, period_type="annual"):
        if symbol == "BAD":
            raise RuntimeError("simulated provider failure")
        return good_data

    provider.get_fundamentals = AsyncMock(side_effect=get_fundamentals)

    result = await ingest_fundamentals(["1010", "BAD"], provider, session_factory)

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 1
    assert "BAD" in result.errors
    assert result.success is False

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="1010").count() == 1
    assert session.query(Stock).filter_by(symbol="BAD").count() == 0
    session.close()
