"""Unit tests for ChangeDetector."""

from datetime import datetime, timezone
from decimal import Decimal

from src.analysis.recommendation.types import Recommendation
from src.domain.models import RecommendationLabel, SymbolIntelligenceRecord
from src.market_intelligence.change_detector import ChangeDetector
from src.market_intelligence.types import ChangeType
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def _record(
    symbol="2222", recommendation=RecommendationLabel.HOLD, confidence=40.0, final_score=40.0,
    target_price=None, risk_level="MEDIUM", technical_score=None, fundamental_score=None,
):
    return SymbolIntelligenceRecord(
        scan_run_id=1, stock_id=1, symbol=symbol, sector="Energy",
        recommendation=recommendation, confidence=Decimal(str(confidence)), final_score=Decimal(str(final_score)),
        target_price=Decimal(str(target_price)) if target_price is not None else None,
        risk_level=risk_level, evaluated_at=datetime.now(timezone.utc), engine_version="1.0.0",
        technical_score=Decimal(str(technical_score)) if technical_score is not None else None,
        fundamental_score=Decimal(str(fundamental_score)) if fundamental_score is not None else None,
    )


def test_no_previous_record_means_no_events_for_that_symbol():
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222"))]
    result = ChangeDetector().detect(outcomes, previous_records={}, previous_scan_run_id=None)
    assert result.events == []
    assert result.new_symbols == ["2222"]


def test_recommendation_change_detected():
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222", recommendation=Recommendation.BUY))]
    previous = {"2222": _record(recommendation=RecommendationLabel.HOLD)}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    events = [e for e in result.events if e.change_type is ChangeType.RECOMMENDATION_CHANGE]
    assert len(events) == 1
    assert events[0].previous_value == "HOLD"
    assert events[0].new_value == "BUY"


def test_no_recommendation_change_event_when_unchanged():
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222", recommendation=Recommendation.HOLD))]
    previous = {"2222": _record(recommendation=RecommendationLabel.HOLD)}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    assert not any(e.change_type is ChangeType.RECOMMENDATION_CHANGE for e in result.events)


def test_confidence_change_below_threshold_is_not_reported(monkeypatch):
    monkeypatch.setenv("MARKET_CONFIDENCE_CHANGE_THRESHOLD", "5.0")
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222", confidence=42.0))]
    previous = {"2222": _record(confidence=40.0)}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    assert not any(e.change_type is ChangeType.CONFIDENCE_CHANGE for e in result.events)


def test_confidence_change_above_threshold_is_reported(monkeypatch):
    monkeypatch.setenv("MARKET_CONFIDENCE_CHANGE_THRESHOLD", "5.0")
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222", confidence=50.0))]
    previous = {"2222": _record(confidence=40.0)}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    events = [e for e in result.events if e.change_type is ChangeType.CONFIDENCE_CHANGE]
    assert len(events) == 1
    assert events[0].delta == 10.0


def test_target_price_change_reported_as_a_percentage_move(monkeypatch):
    monkeypatch.setenv("MARKET_TARGET_PRICE_CHANGE_THRESHOLD_PCT", "5.0")
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222", target_price=110.0))]
    previous = {"2222": _record(target_price=100.0)}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    events = [e for e in result.events if e.change_type is ChangeType.TARGET_PRICE_CHANGE]
    assert len(events) == 1
    assert events[0].delta == 10.0


def test_risk_change_detected():
    from src.analysis.decision.types import RiskLevel

    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222", risk_level=RiskLevel.HIGH))]
    previous = {"2222": _record(risk_level="LOW")}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    events = [e for e in result.events if e.change_type is ChangeType.RISK_CHANGE]
    assert len(events) == 1
    assert events[0].previous_value == "LOW"
    assert events[0].new_value == "HIGH"


def test_new_and_removed_symbols():
    outcomes = [make_outcome(symbol="NEW", decision=make_decision(symbol="NEW"))]
    previous = {"OLD": _record(symbol="OLD")}
    result = ChangeDetector().detect(outcomes, previous, previous_scan_run_id=1)
    assert result.new_symbols == ["NEW"]
    assert result.removed_symbols == ["OLD"]
