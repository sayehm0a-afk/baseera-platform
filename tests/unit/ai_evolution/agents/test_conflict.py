"""Unit tests for E7's material-disagreement trigger -- pure functions
over hand-built `DecisionFactorBreakdown` fixtures."""

from src.ai_evolution.agents.conflict import TensionLevel, should_trigger_debate, tension_level
from src.analysis.decision.types import DecisionFactorBreakdown


def _breakdown(category, points, available=True):
    return DecisionFactorBreakdown(category=category, points=points, weight=0.25, confidence=80.0, available=available)


class TestTensionLevel:
    def test_none_when_technical_or_fundamental_missing(self):
        assert tension_level([_breakdown("Technical Analysis", 10.0)]) is TensionLevel.NONE

    def test_none_when_spread_below_mild_threshold(self):
        breakdown = [_breakdown("Technical Analysis", 10.0), _breakdown("Fundamental Analysis", 8.0)]
        assert tension_level(breakdown) is TensionLevel.NONE

    def test_mild_when_spread_at_least_5(self):
        breakdown = [_breakdown("Technical Analysis", 10.0), _breakdown("Fundamental Analysis", 4.0)]
        assert tension_level(breakdown) is TensionLevel.MILD

    def test_moderate_when_spread_at_least_15(self):
        breakdown = [_breakdown("Technical Analysis", 20.0), _breakdown("Fundamental Analysis", 4.0)]
        assert tension_level(breakdown) is TensionLevel.MODERATE

    def test_high_when_spread_at_least_30(self):
        breakdown = [_breakdown("Technical Analysis", 35.0), _breakdown("Fundamental Analysis", -5.0)]
        assert tension_level(breakdown) is TensionLevel.HIGH

    def test_none_when_a_category_is_unavailable(self):
        breakdown = [_breakdown("Technical Analysis", 35.0), _breakdown("Fundamental Analysis", -5.0, available=False)]
        assert tension_level(breakdown) is TensionLevel.NONE


class TestShouldTriggerDebate:
    def test_false_for_none_and_mild(self):
        mild = [_breakdown("Technical Analysis", 10.0), _breakdown("Fundamental Analysis", 4.0)]
        assert should_trigger_debate(mild) is False

    def test_true_for_moderate_and_high(self):
        moderate = [_breakdown("Technical Analysis", 20.0), _breakdown("Fundamental Analysis", 4.0)]
        assert should_trigger_debate(moderate) is True
