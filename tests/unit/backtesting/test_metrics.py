"""Unit tests for src.backtesting.metrics -- pure functions, hand-built
deterministic fixtures, no database."""

import statistics
from datetime import date

import pytest

from src.backtesting.metrics import (
    EvaluationOutcome,
    average_forward_return,
    breakdown_by,
    calibration_error,
    compute_all_metrics,
    confidence_buckets,
    direction_accuracy,
    downside_deviation,
    full_report,
    loss_rate,
    max_drawdown,
    median_forward_return,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    stop_loss_hit_rate,
    target_price_hit_rate,
    volatility,
    win_rate,
)


def _outcome(**overrides):
    defaults = dict(
        symbol="2222",
        evaluated_at=date(2026, 1, 1),
        recommendation="BUY",
        confidence=70.0,
        total_score=65.0,
    )
    defaults.update(overrides)
    return EvaluationOutcome(**defaults)


# --- direction_accuracy --------------------------------------------------


def test_direction_accuracy_buy_correct_and_incorrect():
    outcomes = [
        _outcome(recommendation="BUY", forward_return_pct=10.0),  # correct
        _outcome(recommendation="BUY", forward_return_pct=-5.0),  # incorrect
    ]
    assert direction_accuracy(outcomes) == 0.5


def test_direction_accuracy_sell_correct_on_price_decline():
    outcomes = [
        _outcome(recommendation="SELL", forward_return_pct=-8.0),  # price fell -> correct SELL call
        _outcome(recommendation="STRONG_SELL", forward_return_pct=3.0),  # price rose -> incorrect
    ]
    assert direction_accuracy(outcomes) == 0.5


def test_direction_accuracy_excludes_hold():
    outcomes = [_outcome(recommendation="HOLD", forward_return_pct=10.0)]
    assert direction_accuracy(outcomes) is None


def test_direction_accuracy_none_when_no_forward_data():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=None)]
    assert direction_accuracy(outcomes) is None


# --- hit rates -----------------------------------------------------------


def test_target_price_hit_rate():
    outcomes = [
        _outcome(hit_target=True), _outcome(hit_target=True), _outcome(hit_target=False),
        _outcome(hit_target=None),  # excluded, unknown
    ]
    assert target_price_hit_rate(outcomes) == pytest.approx(2 / 3)


def test_stop_loss_hit_rate_none_when_all_unknown():
    outcomes = [_outcome(hit_stop_loss=None)]
    assert stop_loss_hit_rate(outcomes) is None


# --- forward return ----------------------------------------------------


def test_average_and_median_forward_return():
    outcomes = [_outcome(forward_return_pct=v) for v in [10.0, 20.0, -6.0]]
    assert average_forward_return(outcomes) == pytest.approx(8.0)
    assert median_forward_return(outcomes) == pytest.approx(10.0)


def test_forward_return_none_when_empty():
    assert average_forward_return([]) is None
    assert median_forward_return([]) is None


# --- win/loss/profit factor ---------------------------------------------


def test_win_loss_and_profit_factor():
    outcomes = [
        _outcome(recommendation="BUY", forward_return_pct=10.0, evaluated_at=date(2026, 1, 1)),
        _outcome(recommendation="BUY", forward_return_pct=-5.0, evaluated_at=date(2026, 1, 2)),
        _outcome(recommendation="BUY", forward_return_pct=20.0, evaluated_at=date(2026, 1, 3)),
    ]
    assert win_rate(outcomes) == pytest.approx(2 / 3)
    assert loss_rate(outcomes) == pytest.approx(1 / 3)
    assert profit_factor(outcomes) == pytest.approx(6.0)  # (10+20)/5


def test_profit_factor_undefined_with_no_losses():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=10.0)]
    assert profit_factor(outcomes) is None


def test_profit_factor_none_with_no_directional_data():
    assert profit_factor([]) is None
    assert profit_factor([_outcome(recommendation="HOLD", forward_return_pct=5.0)]) is None


# --- max drawdown --------------------------------------------------------


def test_max_drawdown_known_sequence():
    outcomes = [
        _outcome(recommendation="BUY", forward_return_pct=10.0, evaluated_at=date(2026, 1, 1)),
        _outcome(recommendation="BUY", forward_return_pct=-5.0, evaluated_at=date(2026, 1, 2)),
        _outcome(recommendation="BUY", forward_return_pct=20.0, evaluated_at=date(2026, 1, 3)),
    ]
    assert max_drawdown(outcomes) == pytest.approx(-0.05, abs=1e-6)


def test_max_drawdown_zero_when_always_winning():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v, evaluated_at=date(2026, 1, i + 1)) for i, v in enumerate([1.0, 2.0, 3.0])]
    assert max_drawdown(outcomes) == pytest.approx(0.0)


def test_max_drawdown_orders_by_evaluated_at_not_list_order():
    outcomes = [
        _outcome(recommendation="BUY", forward_return_pct=20.0, evaluated_at=date(2026, 1, 3)),
        _outcome(recommendation="BUY", forward_return_pct=10.0, evaluated_at=date(2026, 1, 1)),
        _outcome(recommendation="BUY", forward_return_pct=-5.0, evaluated_at=date(2026, 1, 2)),
    ]
    assert max_drawdown(outcomes) == pytest.approx(-0.05, abs=1e-6)


# --- volatility / downside deviation / sharpe / sortino ------------------


def test_volatility_matches_sample_stdev():
    values = [10.0, -5.0, 20.0]
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in values]
    assert volatility(outcomes) == pytest.approx(statistics.stdev(values))


def test_volatility_none_with_fewer_than_two_points():
    assert volatility([_outcome(recommendation="BUY", forward_return_pct=5.0)]) is None
    assert volatility([]) is None


def test_downside_deviation_only_uses_negative_values():
    values = [10.0, -5.0, -15.0, 20.0]
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in values]
    assert downside_deviation(outcomes) == pytest.approx(statistics.stdev([-5.0, -15.0]))


def test_downside_deviation_none_with_fewer_than_two_losses():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in [10.0, -5.0, 20.0]]
    assert downside_deviation(outcomes) is None


def test_sharpe_ratio_positive_for_consistently_positive_pnl():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in [5.0, 8.0, 3.0, 6.0]]
    ratio = sharpe_ratio(outcomes)
    assert ratio is not None and ratio > 0


def test_sharpe_ratio_none_with_zero_volatility():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=5.0) for _ in range(3)]
    assert sharpe_ratio(outcomes) is None  # stdev of identical values is 0


def test_sortino_ratio_none_with_fewer_than_two_losses():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in [5.0, 8.0]]
    assert sortino_ratio(outcomes) is None


def test_sharpe_ratio_annualization():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in [5.0, 8.0, 3.0, 6.0]]
    non_annualized = sharpe_ratio(outcomes)
    annualized = sharpe_ratio(outcomes, periods_per_year=52)
    assert annualized == pytest.approx(non_annualized * (52 ** 0.5))


# --- calibration / confidence buckets -----------------------------------


def test_confidence_buckets_group_and_compute_realized_accuracy():
    outcomes = [
        _outcome(recommendation="BUY", confidence=85.0, forward_return_pct=10.0),  # correct, bucket 80-100
        _outcome(recommendation="BUY", confidence=90.0, forward_return_pct=-5.0),  # incorrect, bucket 80-100
        _outcome(recommendation="BUY", confidence=30.0, forward_return_pct=2.0),  # correct, bucket 20-40
    ]
    buckets = confidence_buckets(outcomes)
    high_bucket = next(b for b in buckets if b["confidence_range"] == "80-100")
    assert high_bucket["count"] == 2
    assert high_bucket["realized_accuracy"] == pytest.approx(0.5)

    low_bucket = next(b for b in buckets if b["confidence_range"] == "20-40")
    assert low_bucket["count"] == 1
    assert low_bucket["realized_accuracy"] == pytest.approx(1.0)


def test_calibration_error_perfect_calibration_is_zero():
    # 100% confidence, 100% correct -> zero calibration error.
    outcomes = [_outcome(recommendation="BUY", confidence=100.0, forward_return_pct=5.0) for _ in range(3)]
    result = calibration_error(outcomes)
    assert result["overall_error"] == pytest.approx(0.0, abs=1e-9)


def test_calibration_error_overconfidence_is_penalized():
    # 100% confidence, but wrong every time -> maximal calibration error.
    outcomes = [_outcome(recommendation="BUY", confidence=100.0, forward_return_pct=-5.0) for _ in range(3)]
    result = calibration_error(outcomes)
    assert result["overall_error"] == pytest.approx(1.0, abs=1e-9)


def test_calibration_error_none_when_no_directional_data():
    assert calibration_error([]) is None


# --- breakdown_by / full_report -----------------------------------------


def test_breakdown_by_groups_correctly():
    outcomes = [
        _outcome(recommendation="BUY", risk_level="LOW", forward_return_pct=5.0),
        _outcome(recommendation="BUY", risk_level="HIGH", forward_return_pct=-3.0),
        _outcome(recommendation="BUY", risk_level=None, forward_return_pct=1.0),
    ]
    grouped = breakdown_by(outcomes, lambda o: o.risk_level)
    assert set(grouped.keys()) == {"LOW", "HIGH", "UNKNOWN"}
    assert grouped["LOW"]["evaluation_count"] == 1


def test_compute_all_metrics_has_every_expected_key():
    outcomes = [_outcome(recommendation="BUY", forward_return_pct=v) for v in [5.0, -2.0, 8.0]]
    result = compute_all_metrics(outcomes)
    expected_keys = {
        "evaluation_count", "direction_accuracy", "target_price_hit_rate", "stop_loss_hit_rate",
        "average_forward_return_pct", "median_forward_return_pct", "win_rate", "loss_rate",
        "profit_factor", "max_drawdown", "volatility", "downside_deviation", "sharpe_ratio",
        "sortino_ratio", "calibration_error",
    }
    assert expected_keys.issubset(result.keys())


def test_full_report_has_every_requested_breakdown():
    outcomes = [
        _outcome(
            recommendation="BUY", risk_level="LOW", time_horizon="SHORT_TERM", sector="Energy",
            market_regime="UPTREND", forward_return_pct=5.0,
        )
    ]
    report = full_report(outcomes)
    assert set(report.keys()) == {
        "overall", "by_recommendation", "by_confidence_bucket", "by_risk_level",
        "by_time_horizon", "by_sector", "by_symbol", "by_market_regime",
    }
    assert "BUY" in report["by_recommendation"]
    assert "LOW" in report["by_risk_level"]
    assert "2222" in report["by_symbol"]


def test_compute_all_metrics_empty_input_is_all_none_not_an_error():
    result = compute_all_metrics([])
    assert result["evaluation_count"] == 0
    assert result["direction_accuracy"] is None
    assert result["sharpe_ratio"] is None
