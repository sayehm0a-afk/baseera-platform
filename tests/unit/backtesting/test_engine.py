"""Unit tests for src.backtesting.engine -- both the small pure helper
functions (deterministic, precise) and full BacktestingEngine.run()
calls against an in-memory SQLite DB seeded with a controlled,
monotonic price series (so forward returns/hit-target-stop are exactly
predictable, not just plausible).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backtesting.baselines import StrategyCall
from src.backtesting.engine import (
    BacktestConfig,
    BacktestingEngine,
    _compute_forward_return,
    _compute_hit_target_stop,
    _evaluation_dates,
    _meets_thresholds,
    _round_trip_cost_pct,
)
from src.backtesting.metrics import EvaluationOutcome
from src.core.db.database import Base
from src.domain.models import DataProvenanceMode, FundamentalSnapshot, PeriodType, PriceBar, RecommendationSnapshot, Stock, Timeframe
from src.analysis.recommendation.types import ScoreContribution


class _AlwaysStrongBullishContributor:
    """A minimal ScoreContributor that always scores maximally bullish,
    regardless of the actual technical/fundamental data -- used to force
    a deterministic STRONG_BUY/LARGE-position call so a test can assert
    on position sizing without depending on what a specific synthetic
    price series happens to make RSI/MACD/etc. read as."""

    name = "technical"
    default_weight = 1.0

    def contribute(self, context) -> ScoreContribution:
        return ScoreContribution(source=self.name, score=95.0, weight=1.0, confidence=95.0, signals=[])


# --- pure helpers ------------------------------------------------------


def test_evaluation_dates_spans_the_range_at_the_configured_frequency():
    dates = _evaluation_dates(date(2026, 1, 1), date(2026, 1, 31), frequency_days=10)
    assert dates == [date(2026, 1, 1), date(2026, 1, 11), date(2026, 1, 21), date(2026, 1, 31)]


def test_evaluation_dates_single_date_when_frequency_exceeds_range():
    dates = _evaluation_dates(date(2026, 1, 1), date(2026, 1, 5), frequency_days=30)
    assert dates == [date(2026, 1, 1)]


def test_evaluation_dates_rejects_nonpositive_frequency():
    with pytest.raises(ValueError):
        _evaluation_dates(date(2026, 1, 1), date(2026, 1, 5), frequency_days=0)


def test_round_trip_cost_doubles_and_converts_bps_to_pct():
    assert _round_trip_cost_pct(transaction_cost_bps=10.0, slippage_bps=5.0) == pytest.approx(0.30)  # 2*(10+5)/100


def test_round_trip_cost_zero_by_default():
    assert _round_trip_cost_pct(0.0, 0.0) == 0.0


def _price_df(closes, start=date(2026, 1, 1)):
    index = pd.date_range(start, periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes], "close": closes, "volume": [1000.0] * len(closes)},
        index=index,
    )


def test_compute_forward_return_basic():
    df = _price_df([100.0, 105.0, 110.0])
    assert _compute_forward_return(entry_price=100.0, holding_df=df, cost_pct=0.0) == pytest.approx(10.0)


def test_compute_forward_return_applies_cost():
    df = _price_df([100.0, 110.0])
    assert _compute_forward_return(entry_price=100.0, holding_df=df, cost_pct=2.0) == pytest.approx(8.0)


def test_compute_forward_return_none_when_no_future_data():
    assert _compute_forward_return(100.0, pd.DataFrame(), 0.0) is None
    assert _compute_forward_return(None, _price_df([100.0]), 0.0) is None


def test_hit_target_stop_bullish_target_hit():
    call = StrategyCall(recommendation="BUY", confidence=70.0, total_score=70.0, target_price=112.0, stop_loss=95.0)
    df = _price_df([100.0, 105.0, 115.0])  # high = close+1, so day 3 high=116 >= 112
    hit_target, hit_stop = _compute_hit_target_stop(call, df)
    assert hit_target is True
    assert hit_stop is False


def test_hit_target_stop_bearish_target_hit_on_decline():
    call = StrategyCall(recommendation="SELL", confidence=70.0, total_score=30.0, target_price=88.0, stop_loss=105.0)
    df = _price_df([100.0, 95.0, 85.0])  # low = close-1, day3 low=84 <= 88
    hit_target, hit_stop = _compute_hit_target_stop(call, df)
    assert hit_target is True
    assert hit_stop is False


def test_hit_target_stop_hold_is_undefined():
    call = StrategyCall(recommendation="HOLD", confidence=50.0, total_score=50.0, target_price=110.0, stop_loss=90.0)
    df = _price_df([100.0, 120.0])
    assert _compute_hit_target_stop(call, df) == (None, None)


def test_hit_target_stop_empty_df_is_unknown():
    call = StrategyCall(recommendation="BUY", confidence=70.0, total_score=70.0, target_price=110.0)
    assert _compute_hit_target_stop(call, pd.DataFrame()) == (None, None)


def test_meets_thresholds_confidence_filter():
    outcome = EvaluationOutcome(symbol="2222", evaluated_at=date(2026, 1, 1), recommendation="BUY", confidence=40.0, total_score=60.0)
    assert not _meets_thresholds(outcome, confidence_threshold=50.0, recommendation_threshold=None)
    assert _meets_thresholds(outcome, confidence_threshold=30.0, recommendation_threshold=None)


def test_meets_thresholds_recommendation_filter():
    buy = EvaluationOutcome(symbol="2222", evaluated_at=date(2026, 1, 1), recommendation="BUY", confidence=70.0, total_score=65.0)
    sell = EvaluationOutcome(symbol="2222", evaluated_at=date(2026, 1, 1), recommendation="SELL", confidence=70.0, total_score=35.0)
    assert _meets_thresholds(buy, None, "BUY")
    assert not _meets_thresholds(sell, None, "BUY")
    assert _meets_thresholds(sell, None, "SELL")


# --- BacktestingEngine.run() -- full DB integration ------------------


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _seed_stock_with_monotonic_bars(session, symbol="2222", count=200, step=0.1, source="dev-synthetic", is_synthetic=True):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        price = 30.0 + i * step
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(round(price, 4))), high=Decimal(str(round(price + 0.2, 4))),
                low=Decimal(str(round(price - 0.2, 4))), close=Decimal(str(round(price, 4))),
                volume=1000 + i, source=source, is_synthetic=is_synthetic,
            )
        )
    session.commit()
    return stock


def _seed_fundamentals(session, stock, fiscal_period_end=date(2025, 12, 31)):
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id, period_type=PeriodType.ANNUAL, fiscal_period_end=fiscal_period_end,
            revenue=Decimal("1000000"), net_income=Decimal("100000"), total_assets=Decimal("5000000"),
            total_liabilities=Decimal("2000000"), total_equity=Decimal("3000000"), current_assets=Decimal("1500000"),
            current_liabilities=Decimal("800000"), shares_outstanding=1_000_000, eps=Decimal("0.1"),
            dividend_per_share=Decimal("0.02"), source="dev-synthetic", is_synthetic=True,
        )
    )
    session.commit()


def _config(**overrides):
    defaults = dict(
        symbols=["2222"],
        start_date=date(2026, 2, 15),
        end_date=date(2026, 5, 1),
        data_provenance_mode=DataProvenanceMode.SYNTHETIC,
        strategy="buy_and_hold",
        evaluation_frequency_days=14,
        holding_horizon_days=20,
        target_price_horizon_days=40,
    )
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def test_run_evaluates_and_persists_snapshots_on_a_monotonic_uptrend(session):
    _seed_stock_with_monotonic_bars(session)
    report = BacktestingEngine().run(session, _config())

    assert report["evaluated_count"] > 0
    assert report["skipped"]["insufficient_data"] == 0
    assert session.query(RecommendationSnapshot).count() == report["evaluated_count"]
    # Buy-and-hold on a monotonic uptrend: every call is a win.
    assert report["overall"]["win_rate"] == pytest.approx(1.0)
    assert report["overall"]["direction_accuracy"] == pytest.approx(1.0)


def test_position_size_flows_through_to_evaluation_outcomes(session):
    # Regression: EvaluationOutcome.position_size used to be left at its
    # dataclass default (None) even though StrategyCall.position_size was
    # already computed and persisted to RecommendationSnapshot -- position
    # sizing quality could never be measured as a result.
    _seed_stock_with_monotonic_bars(session)
    config = _config(strategy="ai_decision_engine", strategy_kwargs={"contributors": [_AlwaysStrongBullishContributor()]})
    report = BacktestingEngine().run(session, config)
    assert report["evaluated_count"] > 0
    assert report["overall"]["position_sizing_quality"] is not None


def test_run_is_idempotent_on_rerun_with_the_same_run_id(session):
    _seed_stock_with_monotonic_bars(session)
    config = _config()
    BacktestingEngine().run(session, config, run_id=1)
    first_count = session.query(RecommendationSnapshot).count()

    BacktestingEngine().run(session, config, run_id=1)  # same run_id, re-executed
    second_count = session.query(RecommendationSnapshot).count()

    assert first_count == second_count
    assert first_count > 0


def test_different_run_ids_do_not_collide(session):
    _seed_stock_with_monotonic_bars(session)
    config = _config()
    BacktestingEngine().run(session, config, run_id=1)
    BacktestingEngine().run(session, config, run_id=2)

    assert session.query(RecommendationSnapshot).filter_by(run_id=1).count() > 0
    assert session.query(RecommendationSnapshot).filter_by(run_id=2).count() > 0


def test_unknown_symbol_is_skipped_not_an_error(session):
    _seed_stock_with_monotonic_bars(session, symbol="2222")
    config = _config(symbols=["9999"])
    report = BacktestingEngine().run(session, config)
    assert report["evaluated_count"] == 0
    assert report["skipped"]["symbol_not_found"] > 0


def test_insufficient_history_is_skipped(session):
    _seed_stock_with_monotonic_bars(session, count=5)  # far too few bars
    config = _config(start_date=date(2026, 1, 3), end_date=date(2026, 1, 5), evaluation_frequency_days=1)
    report = BacktestingEngine().run(session, config)
    assert report["evaluated_count"] == 0
    assert report["skipped"]["insufficient_data"] > 0


def test_provenance_mismatch_is_skipped_not_blended(session):
    _seed_stock_with_monotonic_bars(session, count=100, source="sahmk", is_synthetic=False)
    config = _config(data_provenance_mode=DataProvenanceMode.SYNTHETIC)  # run declares synthetic, data is live
    report = BacktestingEngine().run(session, config)
    assert report["evaluated_count"] == 0
    assert report["skipped"]["provenance_mismatch"] > 0


def test_matching_provenance_is_not_skipped(session):
    _seed_stock_with_monotonic_bars(session, count=100, source="sahmk", is_synthetic=False)
    config = _config(data_provenance_mode=DataProvenanceMode.LIVE)
    report = BacktestingEngine().run(session, config)
    assert report["evaluated_count"] > 0
    assert report["skipped"]["provenance_mismatch"] == 0


def test_transaction_costs_reduce_forward_return(session):
    _seed_stock_with_monotonic_bars(session)
    free = BacktestingEngine().run(session, _config(transaction_cost_bps=0.0, slippage_bps=0.0))
    costly = BacktestingEngine().run(session, _config(transaction_cost_bps=50.0, slippage_bps=50.0))
    assert costly["overall"]["average_forward_return_pct"] < free["overall"]["average_forward_return_pct"]


def test_confidence_threshold_filters_metrics_but_not_persisted_snapshots(session):
    _seed_stock_with_monotonic_bars(session)
    # buy_and_hold always reports confidence=100 -> an impossible threshold excludes everything from metrics.
    report = BacktestingEngine().run(session, _config(confidence_threshold=101.0))
    assert report["evaluated_count"] > 0
    assert report["filtered_count"] == 0
    assert session.query(RecommendationSnapshot).count() == report["evaluated_count"]


def test_cancellation_stops_the_run_early(session):
    _seed_stock_with_monotonic_bars(session)
    config = _config(end_date=date(2026, 12, 1))  # a long range, many evaluation dates

    calls = {"n": 0}

    def is_cancelled():
        calls["n"] += 1
        return calls["n"] > 2  # cancel after a couple of evaluations

    report = BacktestingEngine().run(session, config, is_cancelled=is_cancelled)
    assert report["cancelled"] is True
    assert report["evaluated_count"] < len(_evaluation_dates(config.start_date, config.end_date, config.evaluation_frequency_days))


def test_progress_callback_reaches_the_final_total(session):
    _seed_stock_with_monotonic_bars(session)
    config = _config()
    progress_calls = []
    BacktestingEngine().run(session, config, progress_callback=lambda done, total: progress_calls.append((done, total)))

    assert progress_calls
    final_done, final_total = progress_calls[-1]
    assert final_done == final_total


def test_ai_decision_engine_strategy_end_to_end(session):
    stock = _seed_stock_with_monotonic_bars(session)
    _seed_fundamentals(session, stock)
    config = _config(strategy="ai_decision_engine", start_date=date(2026, 3, 1), end_date=date(2026, 4, 1))
    report = BacktestingEngine().run(session, config)

    assert report["evaluated_count"] > 0
    snapshot = session.query(RecommendationSnapshot).first()
    assert snapshot.recommendation is not None
    assert snapshot.contributor_breakdown is not None
    assert len(snapshot.contributor_breakdown) == 11
