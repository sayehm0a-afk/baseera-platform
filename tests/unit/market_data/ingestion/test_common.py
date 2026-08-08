"""Unit tests for src.market_data.ingestion._common's shared helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.market_data.ingestion._common import UNCLASSIFIED_BUCKET, get_or_create_stock, sleep_if_rate_limited


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_sleeps_for_retry_after():
    """A real production gap this session found: SahmkClient parses a
    429's Retry-After header into SahmkRateLimitError.retry_after, but
    nothing previously read it once the exception reached an ingestion
    job's per-symbol loop -- the very next symbol's request went out
    immediately. This is the fix: honor it."""

    class _RateLimited(Exception):
        retry_after = 12.5

    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(_RateLimited())

    mock_sleep.assert_awaited_once_with(12.5)


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_caps_an_excessive_retry_after():
    class _RateLimited(Exception):
        retry_after = 9999.0

    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(_RateLimited())

    mock_sleep.assert_awaited_once_with(30.0)


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_is_a_noop_without_retry_after():
    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(RuntimeError("some other failure"))

    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_is_a_noop_when_retry_after_is_none():
    class _RateLimited(Exception):
        retry_after = None

    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(_RateLimited())

    mock_sleep.assert_not_awaited()


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


class TestGetOrCreateStockClassificationDefault:
    """Root-cause regression for the real production defect (2026-08-08):
    a bare Stock stub (created by an OHLCV/fundamentals/dividends job
    referencing a symbol that was never classified) used to default to
    is_active=True, silently becoming an ordinary tradeable equity with
    no security-type confirmation at all. The single authority for
    is_active is now universe_policy.classify_universe(), applied via
    ingest_symbols.sync_symbols(); every other caller must get an
    unclassified, inactive stub by default."""

    def test_untrusted_new_stub_defaults_unclassified_and_inactive(self, session_factory):
        session = session_factory()
        stock = get_or_create_stock(session, "6000")
        session.commit()

        assert stock.is_active is False
        assert stock.instrument_bucket == UNCLASSIFIED_BUCKET
        assert stock.exclusion_reason is not None
        session.close()

    def test_trusted_new_stub_keeps_prior_active_default(self, session_factory):
        """The operator's own explicitly-configured symbol seed list
        (INGESTION_SYMBOL_UNIVERSE) is a deliberate, curated decision --
        preserves the pre-fix cold-start behavior exactly."""
        session = session_factory()
        stock = get_or_create_stock(session, "2222", trusted=True)
        session.commit()

        assert stock.is_active is True
        assert stock.instrument_bucket is None
        session.close()

    def test_existing_stock_row_is_returned_unchanged_regardless_of_trusted(self, session_factory):
        session = session_factory()
        first = get_or_create_stock(session, "1120", trusted=True)
        session.commit()
        first.instrument_bucket = "MAIN_MARKET_EQUITY"
        session.commit()

        second = get_or_create_stock(session, "1120", trusted=False)
        assert second.id == first.id
        assert second.instrument_bucket == "MAIN_MARKET_EQUITY"
        session.close()
