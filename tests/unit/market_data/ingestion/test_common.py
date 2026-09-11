"""Unit tests for src.market_data.ingestion._common's shared helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.market_data.ingestion._common import (
    UNCLASSIFIED_BUCKET,
    InvalidPriceBarError,
    get_or_create_stock,
    sleep_if_rate_limited,
    upsert_price_bar,
)


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


class TestUpsertPriceBarStructuralValidation:
    """2026-09 audit finding: no OHLCV bar was ever checked for basic
    structural sanity before being persisted and fed into technical
    analysis. These are the regression tests for the fix -- a pure
    data-integrity gate at the storage boundary, no Decision Engine V2/
    Brain/Shadow/Recurrent Scan logic touched."""

    def _valid_bar(self, **overrides):
        bar = {
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 100000,
            "timestamp": "2026-09-10T00:00:00+00:00",
            "source": "sahmk",
            "is_synthetic": False,
        }
        bar.update(overrides)
        return bar

    def _stock(self, session):
        stock = get_or_create_stock(session, "1010", trusted=True)
        session.commit()
        return stock

    def test_accepts_a_structurally_valid_bar(self, session_factory):
        session = session_factory()
        stock = self._stock(session)
        assert upsert_price_bar(session, stock, self._valid_bar()) is True
        session.close()

    def test_rejects_high_below_low(self, session_factory):
        session = session_factory()
        stock = self._stock(session)
        with pytest.raises(InvalidPriceBarError, match="high.*low"):
            upsert_price_bar(session, stock, self._valid_bar(high=9.0, low=9.8))
        session.close()

    def test_rejects_open_outside_low_high_range(self, session_factory):
        session = session_factory()
        stock = self._stock(session)
        with pytest.raises(InvalidPriceBarError, match="open"):
            upsert_price_bar(session, stock, self._valid_bar(open=11.0, high=10.5, low=9.8))
        session.close()

    def test_rejects_close_outside_low_high_range(self, session_factory):
        session = session_factory()
        stock = self._stock(session)
        with pytest.raises(InvalidPriceBarError, match="close"):
            upsert_price_bar(session, stock, self._valid_bar(close=9.0, high=10.5, low=9.8))
        session.close()

    def test_rejects_non_positive_prices(self, session_factory):
        session = session_factory()
        stock = self._stock(session)
        with pytest.raises(InvalidPriceBarError, match="non-positive"):
            upsert_price_bar(session, stock, self._valid_bar(open=0, high=0, low=0, close=0))
        session.close()

    def test_rejects_negative_volume(self, session_factory):
        session = session_factory()
        stock = self._stock(session)
        with pytest.raises(InvalidPriceBarError, match="volume"):
            upsert_price_bar(session, stock, self._valid_bar(volume=-1))
        session.close()

    def test_nothing_is_written_to_the_session_when_validation_fails(self, session_factory):
        """The check must happen before any DB interaction -- a rejected
        bar must not leave a half-written row or a flushed-but-invalid
        state behind."""
        from src.domain.models import PriceBar

        session = session_factory()
        stock = self._stock(session)
        with pytest.raises(InvalidPriceBarError):
            upsert_price_bar(session, stock, self._valid_bar(high=1.0, low=9.8))
        assert session.query(PriceBar).count() == 0
        session.close()
