"""Unit tests for the Decision & Intelligence Modules value types."""

from datetime import datetime, timezone

from src.analysis.intelligence.contracts.types import (
    MANDATORY_DISCLAIMER_AR,
    MANDATORY_DISCLAIMER_EN,
    AlertEvent,
    AlertRule,
    AlertSeverity,
    DataState,
    DecisionOutput,
    PortfolioAnalysisResult,
    PortfolioPosition,
    RecommendationOutput,
    RecommendationVerdict,
    RiskAssessment,
    RiskLevel,
    ScanCriteria,
    ScanMatch,
    TimeHorizon,
)


def test_recommendation_verdict_has_exactly_the_five_instructed_values():
    assert {v.value for v in RecommendationVerdict} == {
        "watch",
        "suitable_for_speculation",
        "suitable_for_investment",
        "wait",
        "avoid_temporarily",
    }


def test_recommendation_output_carries_mandatory_disclaimer_by_default():
    output = RecommendationOutput(
        symbol="1010",
        verdict=RecommendationVerdict.WATCH,
        confidence=0.5,
        reasons=("evidence a",),
        risks=("risk a",),
        time_horizon=TimeHorizon.MEDIUM_TERM,
        support_levels=(10.0,),
        resistance_levels=(12.0,),
        initial_targets=(11.0,),
        data_state=DataState.LIVE,
        as_of=datetime.now(timezone.utc),
    )
    assert output.disclaimer_ar == MANDATORY_DISCLAIMER_AR
    assert output.disclaimer_en == MANDATORY_DISCLAIMER_EN
    assert "ليس" in output.disclaimer_ar or "not" in output.disclaimer_en.lower()


def test_disclaimer_text_explicitly_disclaims_guaranteed_profit():
    assert "ربح" in MANDATORY_DISCLAIMER_AR or "عائد" in MANDATORY_DISCLAIMER_AR
    assert "profit" in MANDATORY_DISCLAIMER_EN.lower() or "return" in MANDATORY_DISCLAIMER_EN.lower()


def test_portfolio_analysis_result_carries_mandatory_disclaimer_by_default():
    result = PortfolioAnalysisResult(
        positions=(PortfolioPosition(symbol="1010", quantity=10, average_cost=42.0),),
        total_value=420.0,
        concentration_warnings=(),
        risk_level=RiskLevel.MODERATE,
        as_of=datetime.now(timezone.utc),
    )
    assert result.disclaimer_ar == MANDATORY_DISCLAIMER_AR
    assert result.disclaimer_en == MANDATORY_DISCLAIMER_EN


def test_risk_assessment_carries_mandatory_disclaimer_by_default():
    assessment = RiskAssessment(
        symbol="1010",
        risk_level=RiskLevel.HIGH,
        factors=("high volatility",),
        as_of=datetime.now(timezone.utc),
    )
    assert assessment.disclaimer_ar == MANDATORY_DISCLAIMER_AR
    assert assessment.disclaimer_en == MANDATORY_DISCLAIMER_EN


def test_decision_output_carries_mandatory_disclaimer_by_default():
    decision = DecisionOutput(
        symbol="1010",
        verdict=RecommendationVerdict.WAIT,
        confidence=0.3,
        reasoning=("insufficient data",),
        as_of=datetime.now(timezone.utc),
    )
    assert decision.disclaimer_ar == MANDATORY_DISCLAIMER_AR
    assert decision.disclaimer_en == MANDATORY_DISCLAIMER_EN


def test_scan_match_and_alert_event_carry_data_state():
    now = datetime.now(timezone.utc)
    match = ScanMatch(symbol="1010", matched_at=now, reasons=("rsi<30",), data_state=DataState.CACHED)
    assert match.data_state == DataState.CACHED

    event = AlertEvent(
        rule_id="r1", symbol="1010", severity=AlertSeverity.WARNING,
        message="price crossed threshold", triggered_at=now, data_state=DataState.LIVE,
    )
    assert event.data_state == DataState.LIVE


def test_scan_criteria_defaults_to_full_universe():
    criteria = ScanCriteria(filters={"rsi_below": 30})
    assert criteria.universe == ()
    assert criteria.max_results is None


def test_alert_rule_is_constructible_with_a_condition_mapping():
    rule = AlertRule(
        rule_id="r1", symbol="1010",
        condition={"field": "price", "op": ">=", "value": 42.0},
        severity=AlertSeverity.CRITICAL,
    )
    assert rule.condition["value"] == 42.0
