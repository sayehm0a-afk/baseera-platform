"""Unit tests for the Dividend model -- round-trip persistence and the
ex-date uniqueness constraint, no network."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import Dividend, Stock


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


def test_dividend_round_trip(session, stock):
    dividend = Dividend(
        stock_id=stock.id,
        ex_date=date(2026, 6, 1),
        payment_date=date(2026, 7, 1),
        amount_per_share=1.5,
        source="sahmk",
        is_synthetic=False,
    )
    session.add(dividend)
    session.commit()

    fetched = session.query(Dividend).filter_by(stock_id=stock.id).one()
    assert fetched.ex_date == date(2026, 6, 1)
    assert fetched.payment_date == date(2026, 7, 1)
    assert float(fetched.amount_per_share) == 1.5
    assert fetched.source == "sahmk"
    assert fetched.is_synthetic is False


def test_dividend_payment_date_is_optional(session, stock):
    dividend = Dividend(
        stock_id=stock.id,
        ex_date=date(2026, 6, 1),
        amount_per_share=1.0,
        source="dev-synthetic",
        is_synthetic=True,
    )
    session.add(dividend)
    session.commit()
    assert session.query(Dividend).one().payment_date is None


def test_dividend_is_synthetic_defaults_to_false(session, stock):
    dividend = Dividend(
        stock_id=stock.id, ex_date=date(2026, 6, 1), amount_per_share=1.0, source="sahmk"
    )
    session.add(dividend)
    session.commit()
    assert session.query(Dividend).one().is_synthetic is False


def test_dividend_ex_date_is_unique_per_stock(session, stock):
    session.add(
        Dividend(stock_id=stock.id, ex_date=date(2026, 6, 1), amount_per_share=1.0, source="sahmk")
    )
    session.commit()

    session.add(
        Dividend(stock_id=stock.id, ex_date=date(2026, 6, 1), amount_per_share=2.0, source="sahmk")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_dividend_same_ex_date_allowed_for_different_stocks(session, stock):
    other = Stock(symbol="1120", name_en="Al Rajhi Bank")
    session.add(other)
    session.commit()

    session.add(
        Dividend(stock_id=stock.id, ex_date=date(2026, 6, 1), amount_per_share=1.0, source="sahmk")
    )
    session.add(
        Dividend(stock_id=other.id, ex_date=date(2026, 6, 1), amount_per_share=2.0, source="sahmk")
    )
    session.commit()  # must not raise -- different stock_id, same ex_date is fine

    assert session.query(Dividend).count() == 2


def test_dividend_cascade_deletes_with_stock(session, stock):
    session.add(
        Dividend(stock_id=stock.id, ex_date=date(2026, 6, 1), amount_per_share=1.0, source="sahmk")
    )
    session.commit()

    session.delete(stock)
    session.commit()
    assert session.query(Dividend).count() == 0
