"""Unit tests for src.analysis.fundamental.fundamental_loader --
in-memory SQLite, no live DB/network."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.fundamental.fundamental_loader import (
    load_fundamental_snapshots,
    load_latest_fundamental_facts,
)
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


def _add_snapshot(session, stock, year, period_type=PeriodType.ANNUAL):
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=period_type,
            fiscal_period_end=date(year, 12, 31),
            revenue=1000 + year,
            net_income=100 + year,
            total_assets=5000,
            total_liabilities=2000,
            total_equity=3000,
            current_assets=1000,
            current_liabilities=500,
            shares_outstanding=1000,
            eps=0.1,
            source="dev-synthetic",
            is_synthetic=True,
        )
    )


def test_load_fundamental_snapshots_returns_most_recent_first(session, stock):
    _add_snapshot(session, stock, 2022)
    _add_snapshot(session, stock, 2024)
    _add_snapshot(session, stock, 2023)
    session.commit()

    facts = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL)

    assert len(facts) == 3
    assert [f.fiscal_period_end.year for f in facts] == [2024, 2023, 2022]


def test_load_fundamental_snapshots_converts_decimal_to_float(session, stock):
    _add_snapshot(session, stock, 2024)
    session.commit()

    facts = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL)

    assert isinstance(facts[0].revenue, float)
    assert facts[0].revenue == pytest.approx(3024.0)


def test_load_fundamental_snapshots_respects_limit(session, stock):
    for year in range(2018, 2025):
        _add_snapshot(session, stock, year)
    session.commit()

    facts = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL, limit=3)

    assert len(facts) == 3
    assert [f.fiscal_period_end.year for f in facts] == [2024, 2023, 2022]


def test_load_fundamental_snapshots_filters_by_period_type(session, stock):
    _add_snapshot(session, stock, 2024, period_type=PeriodType.ANNUAL)
    _add_snapshot(session, stock, 2024, period_type=PeriodType.QUARTERLY)
    session.commit()

    annual = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL)
    quarterly = load_fundamental_snapshots(session, stock.id, PeriodType.QUARTERLY)

    assert len(annual) == 1
    assert len(quarterly) == 1


def test_load_fundamental_snapshots_empty_result_is_empty_list(session, stock):
    facts = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL)
    assert facts == []


def test_load_latest_fundamental_facts_returns_none_when_empty(session, stock):
    assert load_latest_fundamental_facts(session, stock.id, PeriodType.ANNUAL) is None


def test_load_latest_fundamental_facts_returns_most_recent(session, stock):
    _add_snapshot(session, stock, 2022)
    _add_snapshot(session, stock, 2024)
    session.commit()

    latest = load_latest_fundamental_facts(session, stock.id, PeriodType.ANNUAL)

    assert latest.fiscal_period_end == date(2024, 12, 31)


def test_optional_fields_missing_in_db_are_none_in_facts(session, stock):
    _add_snapshot(session, stock, 2024)  # gross_profit/inventory/etc. not set
    session.commit()

    facts = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL)[0]

    assert facts.gross_profit is None
    assert facts.inventory is None
    assert facts.cash_and_equivalents is None
    assert facts.total_debt is None
