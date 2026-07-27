"""Unit tests for src.backtesting.data_access -- the most
safety-critical module in the Backtesting & Calibration Engine. These
are look-ahead-bias regression tests: every one of them is designed to
fail loudly if a future change lets tomorrow's data leak into today's
decision.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backtesting.data_access import (
    bars_match_provenance,
    collect_as_of_evaluations,
    evaluation_dates,
    load_as_of_dataset,
    load_forward_price_path,
)
from src.core.db.database import Base
from src.domain.models import DataProvenanceMode, FundamentalSnapshot, PeriodType, PriceBar, Stock, Timeframe


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
    s = Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy")
    session.add(s)
    session.commit()
    return s


def _add_bars(session, stock, count, start=date(2026, 1, 1), source="dev-synthetic", is_synthetic=True):
    base = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    for i in range(count):
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=Decimal("30") + i * Decimal("0.1"),
                high=Decimal("31") + i * Decimal("0.1"),
                low=Decimal("29") + i * Decimal("0.1"),
                close=Decimal("30.5") + i * Decimal("0.1"),
                volume=1000 + i,
                source=source,
                is_synthetic=is_synthetic,
            )
        )
    session.commit()


def _add_fundamentals(session, stock, fiscal_period_end):
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=fiscal_period_end,
            revenue=Decimal("1000000"),
            net_income=Decimal("100000"),
            total_assets=Decimal("5000000"),
            total_liabilities=Decimal("2000000"),
            total_equity=Decimal("3000000"),
            current_assets=Decimal("1500000"),
            current_liabilities=Decimal("800000"),
            shares_outstanding=1_000_000,
            eps=Decimal("0.1"),
            dividend_per_share=Decimal("0.02"),
            source="dev-synthetic",
            is_synthetic=True,
        )
    )
    session.commit()


# --- load_as_of_dataset: technical leg -------------------------------


def test_technical_result_never_sees_bars_after_as_of(session, stock):
    _add_bars(session, stock, count=120)  # 2026-01-01 .. 2026-04-30

    cutoff = date(2026, 2, 20)
    dataset = load_as_of_dataset(session, stock, cutoff)

    assert dataset.context.technical_result is not None
    assert dataset.technical_input_as_of.date() <= cutoff
    assert dataset.context.latest_price == pytest.approx(float(Decimal("30.5") + 50 * Decimal("0.1")))


def test_technical_result_is_none_before_the_35_bar_minimum(session, stock):
    _add_bars(session, stock, count=120)

    # Only 10 bars exist on or before this date.
    early_cutoff = date(2026, 1, 10)
    dataset = load_as_of_dataset(session, stock, early_cutoff)

    assert dataset.context.technical_result is None


def test_technical_result_is_none_with_zero_bars(session, stock):
    dataset = load_as_of_dataset(session, stock, date(2026, 1, 1))
    assert dataset.context.technical_result is None
    assert dataset.technical_input_as_of is None
    assert dataset.context.latest_price is None


def test_bars_exactly_on_the_cutoff_date_are_included(session, stock):
    _add_bars(session, stock, count=40)  # 2026-01-01 .. 2026-02-09
    cutoff = date(2026, 2, 9)  # the exact date of the last ingested bar

    dataset = load_as_of_dataset(session, stock, cutoff)
    assert dataset.technical_input_as_of.date() == cutoff


# --- load_as_of_dataset: fundamental leg + reporting lag -------------


def test_fundamental_result_excluded_until_reporting_lag_elapses(session, stock):
    _add_bars(session, stock, count=120)
    _add_fundamentals(session, stock, fiscal_period_end=date(2025, 12, 31))

    # Default 45-day lag: available from 2026-02-14 onward.
    just_before = load_as_of_dataset(session, stock, date(2026, 2, 13))
    just_after = load_as_of_dataset(session, stock, date(2026, 2, 14))

    assert just_before.context.fundamental_result is None
    assert just_after.context.fundamental_result is not None
    assert just_after.fundamental_input_as_of == date(2025, 12, 31)


def test_reporting_lag_is_configurable(session, stock):
    _add_bars(session, stock, count=120)
    _add_fundamentals(session, stock, fiscal_period_end=date(2025, 12, 31))

    dataset = load_as_of_dataset(session, stock, date(2026, 1, 5), fundamental_reporting_lag_days=0)
    assert dataset.context.fundamental_result is not None  # no lag -> available immediately after period end


def test_fundamental_result_never_uses_a_later_fiscal_period(session, stock):
    _add_bars(session, stock, count=200)
    _add_fundamentals(session, stock, fiscal_period_end=date(2025, 12, 31))
    _add_fundamentals(session, stock, fiscal_period_end=date(2026, 12, 31))  # a "future" period, relative to eval date

    dataset = load_as_of_dataset(session, stock, date(2026, 3, 1))

    assert dataset.fundamental_input_as_of == date(2025, 12, 31)  # not the 2026 period


# --- provenance metadata on the snapshot ----------------------------


def test_price_bar_provenance_is_captured(session, stock):
    _add_bars(session, stock, count=40, source="sahmk", is_synthetic=False)
    dataset = load_as_of_dataset(session, stock, date(2026, 2, 5))
    assert dataset.price_bar_source == "sahmk"
    assert dataset.price_bar_is_synthetic is False


# --- load_forward_price_path: intentionally forward-looking, for scoring ---


def test_forward_price_path_excludes_the_evaluation_date_itself(session, stock):
    _add_bars(session, stock, count=60)
    forward = load_forward_price_path(session, stock, from_date=date(2026, 1, 20), horizon_days=10)
    assert forward.index[0].date() == date(2026, 1, 21)


def test_forward_price_path_respects_the_horizon(session, stock):
    _add_bars(session, stock, count=60)
    forward = load_forward_price_path(session, stock, from_date=date(2026, 1, 1), horizon_days=5)
    assert forward.index[-1].date() <= date(2026, 1, 6)
    assert forward.index[-1].date() > date(2026, 1, 1)


def test_forward_price_path_empty_past_available_history(session, stock):
    _add_bars(session, stock, count=10)  # last bar 2026-01-10
    forward = load_forward_price_path(session, stock, from_date=date(2026, 1, 9), horizon_days=30)
    assert len(forward) == 1  # only 2026-01-10 exists


# --- bars_match_provenance ---------------------------------------------


def test_provenance_matches_when_all_bars_are_synthetic(session, stock):
    _add_bars(session, stock, count=30, is_synthetic=True)
    assert bars_match_provenance(session, stock.id, date(2026, 1, 1), date(2026, 1, 30), expect_synthetic=True)
    assert not bars_match_provenance(session, stock.id, date(2026, 1, 1), date(2026, 1, 30), expect_synthetic=False)


def test_provenance_detects_a_mixed_range(session, stock):
    _add_bars(session, stock, count=15, start=date(2026, 1, 1), is_synthetic=True)
    _add_bars(session, stock, count=15, start=date(2026, 1, 16), is_synthetic=False)
    assert not bars_match_provenance(session, stock.id, date(2026, 1, 1), date(2026, 1, 30), expect_synthetic=True)
    assert not bars_match_provenance(session, stock.id, date(2026, 1, 1), date(2026, 1, 30), expect_synthetic=False)


def test_provenance_trivially_matches_when_no_bars_exist(session, stock):
    assert bars_match_provenance(session, stock.id, date(2030, 1, 1), date(2030, 1, 30), expect_synthetic=True)
    assert bars_match_provenance(session, stock.id, date(2030, 1, 1), date(2030, 1, 30), expect_synthetic=False)


# --- evaluation_dates -------------------------------------------------


def test_evaluation_dates_spans_the_range_at_the_configured_frequency():
    dates = evaluation_dates(date(2026, 1, 1), date(2026, 1, 21), frequency_days=10)
    assert dates == [date(2026, 1, 1), date(2026, 1, 11), date(2026, 1, 21)]


def test_evaluation_dates_rejects_nonpositive_frequency():
    with pytest.raises(ValueError):
        evaluation_dates(date(2026, 1, 1), date(2026, 1, 5), frequency_days=0)


# --- collect_as_of_evaluations ------------------------------------------


def test_collect_as_of_evaluations_returns_one_per_symbol_per_date(session, stock):
    _add_bars(session, stock, count=120)
    evaluations, skipped = collect_as_of_evaluations(
        session, ["2222"], date(2026, 2, 15), date(2026, 3, 1), frequency_days=7,
        data_provenance_mode=DataProvenanceMode.SYNTHETIC,
    )
    assert len(evaluations) == 3  # 2026-02-15, 02-22, 03-01
    assert all(e.symbol == "2222" for e in evaluations)
    assert all(e.dataset.context.technical_result is not None for e in evaluations)
    assert skipped == {"symbol_not_found": 0, "provenance_mismatch": 0, "insufficient_data": 0}


def test_collect_as_of_evaluations_skips_unknown_symbol(session, stock):
    _add_bars(session, stock, count=120)
    evaluations, skipped = collect_as_of_evaluations(
        session, ["9999"], date(2026, 2, 15), date(2026, 3, 1), frequency_days=7,
        data_provenance_mode=DataProvenanceMode.SYNTHETIC,
    )
    assert evaluations == []
    assert skipped["symbol_not_found"] == 3


def test_collect_as_of_evaluations_skips_provenance_mismatch(session, stock):
    _add_bars(session, stock, count=60, is_synthetic=True)
    evaluations, skipped = collect_as_of_evaluations(
        session, ["2222"], date(2026, 1, 20), date(2026, 1, 27), frequency_days=7,
        data_provenance_mode=DataProvenanceMode.LIVE,  # declared LIVE but bars are synthetic
    )
    assert evaluations == []
    assert skipped["provenance_mismatch"] == 2


def test_collect_as_of_evaluations_skips_insufficient_data(session, stock):
    _add_bars(session, stock, count=5)  # far too few bars for a technical result
    evaluations, skipped = collect_as_of_evaluations(
        session, ["2222"], date(2026, 1, 1), date(2026, 1, 3), frequency_days=1,
        data_provenance_mode=DataProvenanceMode.SYNTHETIC,
    )
    assert evaluations == []
    assert skipped["insufficient_data"] == 3
