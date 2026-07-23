"""Unit tests for src.analysis.ohlcv_loader -- in-memory SQLite, no
live DB/network."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.types import REQUIRED_OHLCV_COLUMNS
from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stock(session):
    s = Stock(symbol="2222", name_en="Saudi Aramco")
    session.add(s)
    session.commit()
    return s


def _add_bar(session, stock, day, timeframe=Timeframe.ONE_DAY):
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=timeframe,
            timestamp=datetime(2026, 1, day, 10, 0, tzinfo=timezone.utc),
            open=Decimal("32.10"),
            high=Decimal("32.80"),
            low=Decimal("31.90"),
            close=Decimal("32.50") + Decimal(day),
            volume=1_500_000 + day,
        )
    )


def test_load_price_bars_returns_ascending_ordered_dataframe(session, stock):
    _add_bar(session, stock, 5)
    _add_bar(session, stock, 3)
    _add_bar(session, stock, 4)
    session.commit()

    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)

    assert list(df.columns) == list(REQUIRED_OHLCV_COLUMNS)
    assert list(df.index) == sorted(df.index)
    assert len(df) == 3
    assert df.index[0] < df.index[1] < df.index[2]


def test_load_price_bars_converts_decimal_to_float(session, stock):
    _add_bar(session, stock, 1)
    session.commit()

    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)

    assert df["open"].dtype == "float64"
    assert df["close"].iloc[0] == pytest.approx(33.50)


def test_load_price_bars_filters_by_timeframe(session, stock):
    _add_bar(session, stock, 1, timeframe=Timeframe.ONE_DAY)
    _add_bar(session, stock, 2, timeframe=Timeframe.ONE_HOUR)
    session.commit()

    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)

    assert len(df) == 1


def test_load_price_bars_filters_by_stock(session, stock):
    other = Stock(symbol="1010", name_en="Riyad Bank")
    session.add(other)
    session.commit()
    _add_bar(session, stock, 1)
    session.add(
        PriceBar(
            stock_id=other.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
        )
    )
    session.commit()

    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)

    assert len(df) == 1


def test_load_price_bars_respects_start_and_end(session, stock):
    for day in range(1, 6):
        _add_bar(session, stock, day)
    session.commit()

    df = load_price_bars(
        session,
        stock.id,
        Timeframe.ONE_DAY,
        start=datetime(2026, 1, 2, tzinfo=timezone.utc),
        end=datetime(2026, 1, 4, 12, 0, tzinfo=timezone.utc),
    )

    assert len(df) == 3


def test_load_price_bars_empty_result_has_correct_shape(session, stock):
    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)

    assert len(df) == 0
    assert list(df.columns) == list(REQUIRED_OHLCV_COLUMNS)
