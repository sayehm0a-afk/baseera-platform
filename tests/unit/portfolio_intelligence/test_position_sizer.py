"""Unit tests for PositionSizer."""

from src.analysis.decision.types import PositionSize
from src.analysis.recommendation.types import Recommendation
from src.portfolio_intelligence.position_sizer import PositionSizer
from src.portfolio_intelligence.types import PositionAction
from tests.unit.portfolio_intelligence._fixtures import make_decision, make_holding_analysis


def test_strong_sell_means_exit():
    holding = make_holding_analysis(symbol="A", weight=0.1, decision=make_decision(symbol="A", recommendation=Recommendation.STRONG_SELL))
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.EXIT


def test_sell_means_reduce():
    holding = make_holding_analysis(symbol="A", weight=0.1, decision=make_decision(symbol="A", recommendation=Recommendation.SELL))
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.REDUCE


def test_buy_underweight_vs_target_band_means_increase(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_TARGET_WEIGHT_STANDARD", "0.10")
    monkeypatch.setenv("PORTFOLIO_UNDERWEIGHT_DRIFT_THRESHOLD", "0.02")
    holding = make_holding_analysis(
        symbol="A", weight=0.02,
        decision=make_decision(symbol="A", recommendation=Recommendation.BUY, position_size=PositionSize.STANDARD),
    )
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.INCREASE


def test_buy_overweight_vs_target_band_means_reduce(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_TARGET_WEIGHT_SMALL", "0.03")
    monkeypatch.setenv("PORTFOLIO_OVERWEIGHT_DRIFT_THRESHOLD", "0.02")
    holding = make_holding_analysis(
        symbol="A", weight=0.20,
        decision=make_decision(symbol="A", recommendation=Recommendation.BUY, position_size=PositionSize.SMALL),
    )
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.REDUCE


def test_buy_within_target_band_means_hold(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_TARGET_WEIGHT_STANDARD", "0.10")
    monkeypatch.setenv("PORTFOLIO_UNDERWEIGHT_DRIFT_THRESHOLD", "0.05")
    monkeypatch.setenv("PORTFOLIO_OVERWEIGHT_DRIFT_THRESHOLD", "0.05")
    holding = make_holding_analysis(
        symbol="A", weight=0.10,
        decision=make_decision(symbol="A", recommendation=Recommendation.BUY, position_size=PositionSize.STANDARD),
    )
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.HOLD


def test_hold_recommendation_but_over_concentration_threshold_means_reduce(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_POSITION_CONCENTRATION_THRESHOLD", "0.25")
    holding = make_holding_analysis(symbol="A", weight=0.35, decision=make_decision(symbol="A", recommendation=Recommendation.HOLD))
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.REDUCE


def test_hold_recommendation_within_concentration_threshold_means_hold(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_POSITION_CONCENTRATION_THRESHOLD", "0.25")
    holding = make_holding_analysis(symbol="A", weight=0.10, decision=make_decision(symbol="A", recommendation=Recommendation.HOLD))
    action = PositionSizer().size(holding)
    assert action.action is PositionAction.HOLD


def test_action_carries_recommendation_and_confidence():
    holding = make_holding_analysis(symbol="A", weight=0.1, decision=make_decision(symbol="A", recommendation=Recommendation.HOLD, confidence=77.0))
    action = PositionSizer().size(holding)
    assert action.recommendation == "HOLD"
    assert action.confidence == 77.0
    assert action.symbol == "A"
