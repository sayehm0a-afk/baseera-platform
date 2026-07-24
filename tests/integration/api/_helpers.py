"""Shared setup for API integration tests -- deliberately not a
conftest.py (this repository has none anywhere, by design; see
tests/integration/test_registry_reachability_regression.py's own guard
against one silently appearing). Every test module that needs this
imports it explicitly instead.

Builds a real in-memory SQLite session (mirroring test_full_pipeline.py's
own `session_factory` fixture exactly) and overrides main.app's `get_db`
dependency with it -- the standard FastAPI testing pattern -- so routes
run against real, seeded rows through the real ORM, not a mock.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import main
from src.api.dependencies import get_db
from src.core.db.database import Base
from src.domain.models import FundamentalSnapshot, PeriodType, PriceBar, Stock, Timeframe

BAR_COUNT = 40


def make_session() -> Session:
    # check_same_thread=False + StaticPool: TestClient dispatches
    # requests on a worker thread distinct from the one that creates
    # this session, and a plain sqlite:///:memory: engine hands out a
    # *new*, separately-empty in-memory database on each connection
    # checkout by default -- StaticPool forces every checkout to reuse
    # the one connection this engine ever opens, so the tables created
    # below are still there when a route later queries through it. The
    # standard, well-known pattern for testing FastAPI routes against
    # an in-memory SQLite DB; a real Postgres connection has neither
    # limitation, so src/core/db/database.py's actual production engine
    # creation is untouched by this test-only setup.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    return factory()


def make_client(session: Session, raise_server_exceptions: bool = True) -> TestClient:
    """raise_server_exceptions=False is only needed for tests that
    deliberately trigger a genuinely unhandled exception: Starlette's
    ServerErrorMiddleware sends the registered Exception handler's
    response to the client and then re-raises the original exception
    afterward (by design, so an ASGI server can still log the crash) --
    TestClient's default (True) re-raises that into the test process
    too, so inspecting the response the client actually received needs
    this set to False instead."""
    main.app.dependency_overrides[get_db] = lambda: session
    return TestClient(main.app, raise_server_exceptions=raise_server_exceptions)


def clear_overrides() -> None:
    main.app.dependency_overrides.clear()


def seed_stock(session: Session, symbol: str = "1111", name_en: str = "Test Co") -> Stock:
    stock = Stock(symbol=symbol, name_en=name_en, currency="SAR")
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


def seed_price_history(session: Session, stock: Stock, bar_count: int = BAR_COUNT) -> None:
    """Steady uptrend, mirroring test_full_pipeline.py's _make_ohlcv_bars
    shape exactly, so the same real-engine outputs (bullish SuperTrend,
    strong RSI, etc.) are reproducible here."""
    start = date(2024, 1, 1)
    for i in range(bar_count):
        close = 100.0 + i * 1.5
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=datetime.combine(start + timedelta(days=i), datetime.min.time(), tzinfo=timezone.utc),
                open=close - 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=100_000 + i * 100,
            )
        )
    session.commit()


def seed_fundamental_snapshots(session: Session, stock: Stock) -> None:
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=date(2023, 12, 31),
            revenue=800_000_000,
            net_income=80_000_000,
            total_assets=1_000_000_000,
            total_liabilities=400_000_000,
            total_equity=600_000_000,
            current_assets=300_000_000,
            current_liabilities=150_000_000,
            shares_outstanding=100_000_000,
            eps=0.80,
            dividend_per_share=0.20,
            source="test-fixture",
            is_synthetic=True,
        )
    )
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=date(2024, 12, 31),
            revenue=1_000_000_000,
            net_income=100_000_000,
            total_assets=1_100_000_000,
            total_liabilities=420_000_000,
            total_equity=680_000_000,
            current_assets=340_000_000,
            current_liabilities=160_000_000,
            shares_outstanding=100_000_000,
            eps=1.00,
            dividend_per_share=0.25,
            source="test-fixture",
            is_synthetic=True,
        )
    )
    session.commit()
