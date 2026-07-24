"""Unit tests for the FundamentalSnapshot model -- round-trip
persistence, no network."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import FundamentalSnapshot, PeriodType, Stock


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


def test_fundamental_snapshot_round_trip(session, stock):
    snapshot = FundamentalSnapshot(
        stock_id=stock.id,
        period_type=PeriodType.ANNUAL,
        fiscal_period_end=date(2025, 12, 31),
        revenue=440_000_000_000,
        gross_profit=250_000_000_000,
        net_income=120_000_000_000,
        total_assets=650_000_000_000,
        total_liabilities=250_000_000_000,
        total_equity=400_000_000_000,
        current_assets=90_000_000_000,
        current_liabilities=60_000_000_000,
        inventory=15_000_000_000,
        cash_and_equivalents=40_000_000_000,
        total_debt=100_000_000_000,
        shares_outstanding=200_000_000_000,
        eps=0.60,
        dividend_per_share=0.32,
        source="dev-synthetic",
        is_synthetic=True,
    )
    session.add(snapshot)
    session.commit()

    fetched = session.query(FundamentalSnapshot).filter_by(stock_id=stock.id).one()
    assert fetched.period_type == PeriodType.ANNUAL
    assert fetched.fiscal_period_end == date(2025, 12, 31)
    assert fetched.net_income == 120_000_000_000
    assert fetched.is_synthetic is True
    assert fetched.stock.symbol == "2222"


def test_fundamental_snapshot_defaults(session, stock):
    snapshot = FundamentalSnapshot(
        stock_id=stock.id,
        period_type=PeriodType.QUARTERLY,
        fiscal_period_end=date(2025, 9, 30),
        revenue=1000,
        net_income=100,
        total_assets=5000,
        total_liabilities=2000,
        total_equity=3000,
        current_assets=1000,
        current_liabilities=500,
        shares_outstanding=1000,
        eps=0.1,
        source="dev-synthetic",
    )
    session.add(snapshot)
    session.commit()

    fetched = session.query(FundamentalSnapshot).filter_by(stock_id=stock.id).one()
    assert fetched.dividend_per_share == 0
    assert fetched.is_synthetic is False
    assert fetched.gross_profit is None
    assert fetched.inventory is None
    assert fetched.total_debt is None


def test_fundamental_snapshot_identity_uniqueness(session, stock):
    common = dict(
        stock_id=stock.id,
        period_type=PeriodType.ANNUAL,
        fiscal_period_end=date(2025, 12, 31),
        revenue=1000,
        net_income=100,
        total_assets=5000,
        total_liabilities=2000,
        total_equity=3000,
        current_assets=1000,
        current_liabilities=500,
        shares_outstanding=1000,
        eps=0.1,
        source="dev-synthetic",
    )
    session.add(FundamentalSnapshot(**common))
    session.commit()

    session.add(FundamentalSnapshot(**common))
    with pytest.raises(Exception):
        session.commit()


def test_fundamental_snapshot_distinct_period_types_coexist(session, stock):
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=date(2025, 12, 31),
            revenue=1000,
            net_income=100,
            total_assets=5000,
            total_liabilities=2000,
            total_equity=3000,
            current_assets=1000,
            current_liabilities=500,
            shares_outstanding=1000,
            eps=0.1,
            source="dev-synthetic",
        )
    )
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.QUARTERLY,
            fiscal_period_end=date(2025, 12, 31),
            revenue=250,
            net_income=25,
            total_assets=5000,
            total_liabilities=2000,
            total_equity=3000,
            current_assets=1000,
            current_liabilities=500,
            shares_outstanding=1000,
            eps=0.025,
            source="dev-synthetic",
        )
    )
    session.commit()

    assert session.query(FundamentalSnapshot).filter_by(stock_id=stock.id).count() == 2
