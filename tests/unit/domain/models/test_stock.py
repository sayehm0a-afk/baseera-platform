"""Unit tests for the Stock model -- round-trip persistence, no network."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import Market, Stock


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_stock_round_trip(session):
    stock = Stock(symbol="1010", name_en="Riyad Bank", name_ar="بنك الرياض", sector="Banks")
    session.add(stock)
    session.commit()

    fetched = session.query(Stock).filter_by(symbol="1010").one()
    assert fetched.name_en == "Riyad Bank"
    assert fetched.name_ar == "بنك الرياض"
    assert fetched.sector == "Banks"
    assert fetched.currency == "SAR"
    assert fetched.lot_size == 1
    assert fetched.is_active is True
    assert fetched.created_at is not None
    assert fetched.market == Market.TADAWUL  # default -- see Market's own docstring


def test_stock_symbol_must_be_unique(session):
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank"))
    session.commit()

    session.add(Stock(symbol="1120", name_en="Duplicate"))
    with pytest.raises(Exception):
        session.commit()


def test_stock_market_defaults_to_tadawul_for_a_row_that_never_set_it(session):
    """Every Stock ingested before the `market` column existed (or via
    SAHMK today) must read back as TADAWUL, never a fabricated/blank
    market -- product decision 2026-09-18 multi-market expansion."""
    session.add(Stock(symbol="2222", name_en="Saudi Aramco"))
    session.commit()

    fetched = session.query(Stock).filter_by(symbol="2222").one()
    assert fetched.market == Market.TADAWUL


def test_stock_can_be_created_on_the_us_market(session):
    session.add(Stock(symbol="AAPL", name_en="Apple Inc.", currency="USD", market=Market.US))
    session.commit()

    fetched = session.query(Stock).filter_by(symbol="AAPL").one()
    assert fetched.market == Market.US
    assert fetched.currency == "USD"
