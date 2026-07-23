"""Unit tests for the MarketSnapshot model -- round-trip persistence, no network."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import MarketSnapshot


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_market_snapshot_round_trip(session):
    ts = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot(
        index_name="TASI",
        timestamp=ts,
        value=Decimal("11500.25"),
        change=Decimal("42.10"),
        change_percent=Decimal("0.37"),
        volume=250_000_000,
    )
    session.add(snapshot)
    session.commit()

    fetched = session.query(MarketSnapshot).filter_by(index_name="TASI").one()
    # SQLite (used here for a fast, isolated round-trip) doesn't preserve
    # tzinfo on DateTime(timezone=True); Postgres, the real target, does.
    assert fetched.timestamp == ts.replace(tzinfo=None)
    assert fetched.value == Decimal("11500.25")
    assert fetched.change_percent == Decimal("0.37")


def test_market_snapshot_identity_uniqueness(session):
    ts = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
    session.add(MarketSnapshot(index_name="TASI", timestamp=ts, value=Decimal("1")))
    session.commit()

    session.add(MarketSnapshot(index_name="TASI", timestamp=ts, value=Decimal("2")))
    with pytest.raises(Exception):
        session.commit()
