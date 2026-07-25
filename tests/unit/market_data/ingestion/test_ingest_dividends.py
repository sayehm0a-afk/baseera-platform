"""Unit tests for ingest_dividends -- in-memory SQLite, no live
DB/network."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import Dividend, Stock
from src.market_data.ingestion.ingest_dividends import ingest_dividends
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_ingests_dividend_history(session_factory):
    provider = DevFundamentalDataProvider()

    result = await ingest_dividends(["2222"], provider, session_factory)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 4  # DevFundamentalDataProvider default: 2 years x 2/year

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    dividends = session.query(Dividend).filter_by(stock_id=stock.id).all()
    assert len(dividends) == 4
    for d in dividends:
        assert d.source == "dev-synthetic"
        assert d.is_synthetic is True
    session.close()


@pytest.mark.asyncio
async def test_is_idempotent_no_duplicate_rows_on_rerun(session_factory):
    provider = DevFundamentalDataProvider()
    await ingest_dividends(["2222"], provider, session_factory)
    await ingest_dividends(["2222"], provider, session_factory)

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    assert session.query(Dividend).filter_by(stock_id=stock.id).count() == 4
    session.close()


@pytest.mark.asyncio
async def test_updates_existing_dividend_when_amount_changes(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_dividends = AsyncMock(
        return_value=[
            {
                "dividend_per_share": 1.0,
                "ex_date": "2026-06-01",
                "payment_date": "2026-07-01",
                "source": "sahmk",
                "is_synthetic": False,
            }
        ]
    )

    await ingest_dividends(["2222"], provider, session_factory)

    provider.get_dividends = AsyncMock(
        return_value=[
            {
                "dividend_per_share": 1.5,  # changed
                "ex_date": "2026-06-01",  # same ex_date -- must update, not duplicate
                "payment_date": "2026-07-01",
                "source": "sahmk",
                "is_synthetic": False,
            }
        ]
    )
    result = await ingest_dividends(["2222"], provider, session_factory)
    assert result.rows_upserted == 1

    session = session_factory()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    dividends = session.query(Dividend).filter_by(stock_id=stock.id).all()
    assert len(dividends) == 1
    assert float(dividends[0].amount_per_share) == 1.5
    session.close()


@pytest.mark.asyncio
async def test_skips_records_with_no_ex_date(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)
    provider.get_dividends = AsyncMock(
        return_value=[{"dividend_per_share": 1.0, "payment_date": "2026-07-01"}]  # no ex_date
    )

    result = await ingest_dividends(["2222"], provider, session_factory)
    assert result.symbols_succeeded == 1
    assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_skipped_entirely_when_provider_has_no_dividend_support(session_factory):
    provider = AsyncMock(spec=["authenticate", "disconnect"])
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    result = await ingest_dividends(["2222"], provider, session_factory)

    assert result.symbols_requested == 1
    assert result.symbols_succeeded == 0
    assert result.symbols_failed == 0
    assert result.rows_upserted == 0

    session = session_factory()
    assert session.query(Stock).count() == 0  # nothing was ever attempted
    session.close()


@pytest.mark.asyncio
async def test_isolates_per_symbol_failures(session_factory):
    provider = AsyncMock()
    provider.authenticate = AsyncMock(return_value=True)
    provider.disconnect = AsyncMock(return_value=None)

    async def get_dividends(symbol):
        if symbol == "BAD":
            raise RuntimeError("simulated provider failure")
        return [
            {
                "dividend_per_share": 1.0,
                "ex_date": "2026-06-01",
                "source": "sahmk",
                "is_synthetic": False,
            }
        ]

    provider.get_dividends = AsyncMock(side_effect=get_dividends)

    result = await ingest_dividends(["2222", "BAD"], provider, session_factory)

    assert result.symbols_succeeded == 1
    assert result.symbols_failed == 1
    assert "BAD" in result.errors

    session = session_factory()
    assert session.query(Stock).filter_by(symbol="2222").count() == 1
    assert session.query(Stock).filter_by(symbol="BAD").count() == 0
    session.close()
