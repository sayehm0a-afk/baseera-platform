"""End-to-end proof that the ingestion scheduler actually populates the
database: real ingestion jobs (sync_symbols, ingest_historical_ohlcv,
ingest_fundamentals, ingest_dividends), a real in-memory SQLite DB, and
the real Dev* providers (no network, fully deterministic) -- run
through run_ingestion_job exactly as the scheduler's _loop does, not a
shortcut around it.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import Dividend, FundamentalSnapshot, IngestionJobStatus, PriceBar, Stock
from src.market_data.ingestion.scheduler import IngestionScheduler, run_ingestion_job
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _universe(monkeypatch):
    monkeypatch.setenv("INGESTION_SYMBOL_UNIVERSE", "2222,1120")
    # Small, fixed backfill window so bar counts in these tests are exact
    # and fast to compute, rather than depending on the 90-day production
    # default (get_ohlcv_backfill_days) -- inclusive of both endpoints, a
    # 5-day window backfills 6 bars per symbol.
    monkeypatch.setenv("INGESTION_OHLCV_BACKFILL_DAYS", "5")


@pytest.mark.asyncio
async def test_scheduler_jobs_populate_every_table_from_empty(session_factory):
    async def get_market_provider():
        return DevMarketDataProvider()

    async def get_fundamental_provider():
        return DevFundamentalDataProvider()

    scheduler = IngestionScheduler(
        session_factory=session_factory,
        market_provider_getter=get_market_provider,
        fundamental_provider_getter=get_fundamental_provider,
    )

    session = session_factory()
    assert session.query(Stock).count() == 0
    assert session.query(PriceBar).count() == 0
    assert session.query(FundamentalSnapshot).count() == 0
    assert session.query(Dividend).count() == 0
    session.close()

    symbols_log = await run_ingestion_job("symbols", scheduler._run_symbols, session_factory)
    ohlcv_log = await run_ingestion_job(
        "historical_ohlcv", scheduler._run_historical_ohlcv, session_factory
    )
    fundamentals_log = await run_ingestion_job(
        "fundamentals", scheduler._run_fundamentals, session_factory
    )
    dividends_log = await run_ingestion_job("dividends", scheduler._run_dividends, session_factory)

    for log in (symbols_log, ohlcv_log, fundamentals_log, dividends_log):
        assert log.status == IngestionJobStatus.SUCCESS
        assert log.finished_at is not None
        assert log.duration_seconds is not None

    session = session_factory()
    assert session.query(Stock).count() == 2  # 2222, 1120
    assert session.query(PriceBar).count() == 12  # 6-day backfill (0..5 inclusive) x 2 symbols
    assert session.query(FundamentalSnapshot).count() == 2
    assert session.query(Dividend).count() == 8  # 2 symbols x 4 dividends each (default years_back=2)

    for stock in session.query(Stock).all():
        assert stock.symbol in ("2222", "1120")
    for bar in session.query(PriceBar).all():
        assert bar.open > 0
    for snapshot in session.query(FundamentalSnapshot).all():
        assert snapshot.source == "dev-synthetic"
        assert snapshot.is_synthetic is True
    for dividend in session.query(Dividend).all():
        assert dividend.source == "dev-synthetic"
        assert dividend.is_synthetic is True
    session.close()


@pytest.mark.asyncio
async def test_rerunning_all_jobs_is_idempotent(session_factory):
    async def get_market_provider():
        return DevMarketDataProvider()

    async def get_fundamental_provider():
        return DevFundamentalDataProvider()

    scheduler = IngestionScheduler(
        session_factory=session_factory,
        market_provider_getter=get_market_provider,
        fundamental_provider_getter=get_fundamental_provider,
    )

    for _ in range(2):
        await run_ingestion_job("symbols", scheduler._run_symbols, session_factory)
        await run_ingestion_job("historical_ohlcv", scheduler._run_historical_ohlcv, session_factory)
        await run_ingestion_job("fundamentals", scheduler._run_fundamentals, session_factory)
        await run_ingestion_job("dividends", scheduler._run_dividends, session_factory)

    session = session_factory()
    assert session.query(Stock).count() == 2
    assert session.query(PriceBar).count() == 12  # same backfilled bars, upserted not duplicated
    assert session.query(FundamentalSnapshot).count() == 2
    assert session.query(Dividend).count() == 8
    session.close()

    # Every job run (8 total across 2 cycles x 4 jobs) is durably logged.
    from src.domain.models import IngestionRunLog

    session = session_factory()
    assert session.query(IngestionRunLog).count() == 8
    session.close()


@pytest.mark.asyncio
async def test_provider_outage_falls_back_gracefully_without_corrupting_prior_data(
    session_factory,
):
    """A provider that fails mid-incremental-catch-up must not
    delete/corrupt bars already in the database -- each job run is
    independent and additive. Seeds one *stale* bar directly (a few
    days old, not up to today) so the incremental job still has a real
    gap to fetch and therefore actually calls the (failing) provider,
    rather than short-circuiting as "already up to date" like it
    correctly would against a fresh backfill that already reached
    today."""
    from datetime import timedelta
    from decimal import Decimal

    from src.domain.models import Timeframe

    session = session_factory()
    stock = Stock(symbol="2222", name_en="Stock 2222")
    session.add(stock)
    session.commit()
    stale_day = datetime.now(timezone.utc) - timedelta(days=3)
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=stale_day.replace(hour=0, minute=0, second=0, microsecond=0),
            open=Decimal("10"), high=Decimal("11"), low=Decimal("9"), close=Decimal("10.5"),
            volume=1000,
        )
    )
    session.commit()
    session.close()

    async def failing_provider():
        class _Down:
            async def authenticate(self):
                return False

            async def disconnect(self):
                pass

            async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
                raise RuntimeError("provider unreachable")

        return _Down()

    scheduler_down = IngestionScheduler(
        session_factory=session_factory,
        market_provider_getter=failing_provider,
        fundamental_provider_getter=failing_provider,
    )
    log = await run_ingestion_job(
        "historical_ohlcv", scheduler_down._run_historical_ohlcv, session_factory
    )
    assert log.status == IngestionJobStatus.FAILED
    assert log.symbols_failed == 2  # both "2222" (stale) and "1120" (never ingested) attempt a fetch

    session = session_factory()
    assert session.query(PriceBar).count() == 1  # the stale seed bar is still there, untouched
    session.close()
