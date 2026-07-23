"""Unit tests for the PriceBar model -- round-trip persistence, no network."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


def test_price_bar_round_trip(session, stock):
    ts = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    bar = PriceBar(
        stock_id=stock.id,
        timeframe=Timeframe.ONE_DAY,
        timestamp=ts,
        open=Decimal("32.10"),
        high=Decimal("32.80"),
        low=Decimal("31.90"),
        close=Decimal("32.50"),
        volume=1_500_000,
    )
    session.add(bar)
    session.commit()

    fetched = session.query(PriceBar).filter_by(stock_id=stock.id).one()
    assert fetched.timeframe == Timeframe.ONE_DAY
    # SQLite (used here for a fast, isolated round-trip) doesn't preserve
    # tzinfo on DateTime(timezone=True); Postgres, the real target, does.
    assert fetched.timestamp == ts.replace(tzinfo=None)
    assert fetched.open == Decimal("32.10")
    assert fetched.close == Decimal("32.50")
    assert fetched.volume == 1_500_000
    assert fetched.stock.symbol == "2222"


def test_price_bar_identity_uniqueness(session, stock):
    ts = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=ts,
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
        )
    )
    session.commit()

    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=ts,
            open=Decimal("2"),
            high=Decimal("2"),
            low=Decimal("2"),
            close=Decimal("2"),
        )
    )
    with pytest.raises(Exception):
        session.commit()
