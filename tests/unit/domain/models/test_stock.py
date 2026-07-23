"""Unit tests for the Stock model -- round-trip persistence, no network."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import Stock


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


def test_stock_symbol_must_be_unique(session):
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank"))
    session.commit()

    session.add(Stock(symbol="1120", name_en="Duplicate"))
    with pytest.raises(Exception):
        session.commit()
