"""Unit tests for AlertEngine."""

from datetime import datetime, timezone

from src.market_intelligence.alert_engine import AlertEngine
from src.market_intelligence.types import (
    AlertType,
    ChangeDetectionResult,
    ChangeEvent,
    ChangeType,
    SectorSummary,
)
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome

_NOW = datetime.now(timezone.utc)


def _change_result(events):
    return ChangeDetectionResult(events=events, new_symbols=[], removed_symbols=[], previous_scan_run_id=1)


def test_new_strong_buy_alert():
    events = [ChangeEvent(symbol="A", change_type=ChangeType.RECOMMENDATION_CHANGE, previous_value="HOLD", new_value="STRONG_BUY", delta=None, detected_at=_NOW)]
    alerts = AlertEngine().generate([make_outcome(symbol="A")], _change_result(events), [])
    assert any(a.alert_type is AlertType.NEW_STRONG_BUY for a in alerts)


def test_upgrade_and_downgrade_alerts():
    events = [
        ChangeEvent(symbol="A", change_type=ChangeType.RECOMMENDATION_CHANGE, previous_value="HOLD", new_value="BUY", delta=None, detected_at=_NOW),
        ChangeEvent(symbol="B", change_type=ChangeType.RECOMMENDATION_CHANGE, previous_value="BUY", new_value="HOLD", delta=None, detected_at=_NOW),
    ]
    alerts = AlertEngine().generate([make_outcome(symbol="A"), make_outcome(symbol="B")], _change_result(events), [])
    types = {(a.symbol, a.alert_type) for a in alerts}
    assert ("A", AlertType.RECOMMENDATION_UPGRADED) in types
    assert ("B", AlertType.RECOMMENDATION_DOWNGRADED) in types


def test_confidence_above_threshold_alert(monkeypatch):
    monkeypatch.setenv("MARKET_ALERT_CONFIDENCE_THRESHOLD", "85.0")
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", confidence=90.0)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", confidence=50.0)),
    ]
    alerts = AlertEngine().generate(outcomes, _change_result([]), [])
    confidence_alerts = [a for a in alerts if a.alert_type is AlertType.CONFIDENCE_ABOVE_THRESHOLD]
    assert [a.symbol for a in confidence_alerts] == ["A"]


def test_target_reached_for_a_buy_rated_symbol():
    from src.analysis.recommendation.types import Recommendation

    outcomes = [make_outcome(symbol="A", latest_price=110.0, decision=make_decision(symbol="A", recommendation=Recommendation.BUY, target_price=105.0))]
    alerts = AlertEngine().generate(outcomes, _change_result([]), [])
    assert any(a.alert_type is AlertType.TARGET_REACHED and a.symbol == "A" for a in alerts)


def test_target_not_reached_when_price_below_target():
    from src.analysis.recommendation.types import Recommendation

    outcomes = [make_outcome(symbol="A", latest_price=90.0, decision=make_decision(symbol="A", recommendation=Recommendation.BUY, target_price=105.0))]
    alerts = AlertEngine().generate(outcomes, _change_result([]), [])
    assert not any(a.alert_type is AlertType.TARGET_REACHED for a in alerts)


def test_risk_spike_requires_both_risk_worsening_and_confidence_drop(monkeypatch):
    monkeypatch.setenv("MARKET_ALERT_RISK_SPIKE_CONFIDENCE_DROP", "10.0")
    outcomes = [make_outcome(symbol="A")]

    # Risk worsened but confidence barely moved -- no spike.
    events_no_spike = [
        ChangeEvent(symbol="A", change_type=ChangeType.RISK_CHANGE, previous_value="LOW", new_value="HIGH", delta=None, detected_at=_NOW),
        ChangeEvent(symbol="A", change_type=ChangeType.CONFIDENCE_CHANGE, previous_value="70", new_value="68", delta=-2.0, detected_at=_NOW),
    ]
    alerts = AlertEngine().generate(outcomes, _change_result(events_no_spike), [])
    assert not any(a.alert_type is AlertType.RISK_SPIKE for a in alerts)

    # Risk worsened and confidence dropped sharply -- spike.
    events_spike = [
        ChangeEvent(symbol="A", change_type=ChangeType.RISK_CHANGE, previous_value="LOW", new_value="HIGH", delta=None, detected_at=_NOW),
        ChangeEvent(symbol="A", change_type=ChangeType.CONFIDENCE_CHANGE, previous_value="70", new_value="55", delta=-15.0, detected_at=_NOW),
    ]
    alerts = AlertEngine().generate(outcomes, _change_result(events_spike), [])
    assert any(a.alert_type is AlertType.RISK_SPIKE for a in alerts)


def test_sector_rotation_alert_above_momentum_threshold(monkeypatch):
    monkeypatch.setenv("MARKET_SECTOR_ROTATION_MOMENTUM_THRESHOLD", "5.0")
    summaries = [
        SectorSummary(
            sector="Energy", symbol_count=5, average_confidence=70.0, average_final_score=70.0,
            average_expected_return_pct=5.0, average_technical_score=60.0, average_fundamental_score=60.0,
            buy_count=3, sell_count=1, hold_count=1, breadth=0.6, momentum=10.0,
        ),
    ]
    alerts = AlertEngine().generate([], _change_result([]), summaries)
    assert any(a.alert_type is AlertType.SECTOR_ROTATION and a.sector == "Energy" for a in alerts)


def test_no_sector_rotation_alert_below_threshold(monkeypatch):
    monkeypatch.setenv("MARKET_SECTOR_ROTATION_MOMENTUM_THRESHOLD", "5.0")
    summaries = [
        SectorSummary(
            sector="Energy", symbol_count=5, average_confidence=70.0, average_final_score=70.0,
            average_expected_return_pct=5.0, average_technical_score=60.0, average_fundamental_score=60.0,
            buy_count=3, sell_count=1, hold_count=1, breadth=0.6, momentum=1.0,
        ),
    ]
    alerts = AlertEngine().generate([], _change_result([]), summaries)
    assert not any(a.alert_type is AlertType.SECTOR_ROTATION for a in alerts)
