"""Unit tests for NarrativeBuilder -- fully synchronous and
deterministic, so every method can be asserted on exact, reproducible
output. Uses tiny fakes for TechnicalAnalysisResult/
FundamentalAnalysisResult (same shape: `.indicators`/`.ratios` dicts of
objects with `.latest()`/`.value`) rather than running the real
engines, isolating this module from theirs -- their own test files
already cover indicator/ratio correctness.
"""

from src.analysis.analyst.narrative_builder import NarrativeBuilder
from src.analysis.analyst.signal_interpreter import SignalInterpreter
from src.analysis.decision.types import TimeHorizon
from src.analysis.recommendation.types import SignalDirection
from tests.unit.analysis.analyst._fixtures import make_breakdown, make_decision, make_evidence, make_signal


class _FakeIndicatorOutput:
    def __init__(self, value):
        self._value = value

    def latest(self):
        return self._value


class _FakeTechnicalResult:
    def __init__(self, indicators):
        self.indicators = indicators


class _FakeRatioOutput:
    def __init__(self, value):
        self.value = value


class _FakeFundamentalResult:
    def __init__(self, ratios):
        self.ratios = ratios


def _interpreted(evidence):
    return SignalInterpreter().interpret(evidence)


# --- technical reasoning -----------------------------------------------


def test_technical_reasoning_honest_fallback_when_unavailable():
    evidence = make_evidence(technical_result=None, signals=[], contributor_breakdown=[])
    text = NarrativeBuilder().build_technical_reasoning(evidence, _interpreted(evidence))
    assert "could not be produced" in text
    assert "2222" in text


def test_technical_reasoning_cites_indicator_values_and_factors():
    technical_result = _FakeTechnicalResult(
        {
            "rsi_14": _FakeIndicatorOutput(60.234),
            "adx_14": _FakeIndicatorOutput(28.5),
            "macd": _FakeIndicatorOutput({"macd_line": 0.5, "signal_line": 0.3, "histogram": 0.2}),
        }
    )
    breakdown = [make_breakdown(category="Technical Analysis", points=15.0)]
    signals = [make_signal(name="rsi", source="technical", direction=SignalDirection.BULLISH, impact=15.0)]
    evidence = make_evidence(technical_result=technical_result, signals=signals, contributor_breakdown=breakdown)

    text = NarrativeBuilder().build_technical_reasoning(evidence, _interpreted(evidence))

    assert "RSI(14) at 60.23" in text
    assert "ADX(14) at 28.50" in text
    assert "MACD histogram at 0.20" in text
    assert "bullish" in text


def test_technical_reasoning_handles_missing_individual_indicators_gracefully():
    technical_result = _FakeTechnicalResult({})  # registered but nothing computed for this symbol
    evidence = make_evidence(technical_result=technical_result, signals=[], contributor_breakdown=[])

    text = NarrativeBuilder().build_technical_reasoning(evidence, _interpreted(evidence))

    assert "no indicator readings were available" in text


# --- fundamental reasoning -----------------------------------------------


def test_fundamental_reasoning_honest_fallback_when_unavailable():
    evidence = make_evidence(fundamental_result=None, signals=[], contributor_breakdown=[])
    text = NarrativeBuilder().build_fundamental_reasoning(evidence, _interpreted(evidence))
    assert "could not be produced" in text
    assert "no ingested financial statements" in text


def test_fundamental_reasoning_cites_ratio_values():
    fundamental_result = _FakeFundamentalResult(
        {
            "return_on_equity": _FakeRatioOutput(0.18),
            "net_profit_margin": _FakeRatioOutput(0.12),
            "price_to_earnings": _FakeRatioOutput(15.5),
        }
    )
    evidence = make_evidence(fundamental_result=fundamental_result, signals=[], contributor_breakdown=[])

    text = NarrativeBuilder().build_fundamental_reasoning(evidence, _interpreted(evidence))

    assert "ROE at 0.18" in text
    assert "net margin at 0.12" in text
    assert "P/E at 15.50" in text


def test_fundamental_reasoning_handles_missing_ratios_gracefully():
    fundamental_result = _FakeFundamentalResult({})
    evidence = make_evidence(fundamental_result=fundamental_result, signals=[], contributor_breakdown=[])

    text = NarrativeBuilder().build_fundamental_reasoning(evidence, _interpreted(evidence))

    assert "no ratio readings were available" in text


# --- risk explanation -----------------------------------------------------


def test_risk_explanation_cites_risk_level_and_position_size():
    decision = make_decision()
    evidence = make_evidence(decision=decision, signals=[], contributor_breakdown=[])
    text = NarrativeBuilder().build_risk_explanation(evidence, _interpreted(evidence))
    assert decision.risk_level.value.title() in text
    assert decision.position_size.value.title() in text


# --- target price / stop loss ---------------------------------------------


def test_target_price_explanation_present_when_computable():
    decision = make_decision(target_price=105.0, expected_return_pct=5.0)
    evidence = make_evidence(decision=decision)
    text = NarrativeBuilder().build_target_price_explanation(evidence)
    assert "105.00" in text
    assert "5.00%" in text
    assert "100.00" in text  # reconstructed reference price


def test_target_price_explanation_unavailable_when_no_target():
    decision = make_decision(target_price=None, expected_return_pct=None)
    evidence = make_evidence(decision=decision, technical_result=None)
    text = NarrativeBuilder().build_target_price_explanation(evidence)
    assert "could not be computed" in text


def test_stop_loss_explanation_present_when_computable():
    decision = make_decision(target_price=105.0, expected_return_pct=5.0, stop_loss=97.0)
    evidence = make_evidence(decision=decision)
    text = NarrativeBuilder().build_stop_loss_explanation(evidence)
    assert "97.00" in text
    assert "100.00" in text


def test_stop_loss_explanation_unavailable_when_no_reference_price():
    decision = make_decision(target_price=None, expected_return_pct=None, stop_loss=97.0)
    evidence = make_evidence(decision=decision, technical_result=None)
    text = NarrativeBuilder().build_stop_loss_explanation(evidence)
    assert "could not be computed" in text


def test_reference_price_falls_back_to_bollinger_midpoint():
    technical_result = _FakeTechnicalResult({"bollinger": _FakeIndicatorOutput({"middle": 50.0})})
    decision = make_decision(target_price=None, expected_return_pct=None, stop_loss=45.0)
    evidence = make_evidence(decision=decision, technical_result=technical_result)
    text = NarrativeBuilder().build_stop_loss_explanation(evidence)
    assert "50.00" in text


# --- time horizon -----------------------------------------------------------


def test_time_horizon_explanation_includes_adx_when_available():
    technical_result = _FakeTechnicalResult({"adx_14": _FakeIndicatorOutput(30.0)})
    decision = make_decision(time_horizon=TimeHorizon.LONG_TERM)
    evidence = make_evidence(decision=decision, technical_result=technical_result)
    text = NarrativeBuilder().build_time_horizon_explanation(evidence)
    assert "long-term" in text
    assert "ADX at 30.00" in text


def test_time_horizon_explanation_without_adx():
    decision = make_decision(time_horizon=TimeHorizon.SHORT_TERM)
    evidence = make_evidence(decision=decision, technical_result=None)
    text = NarrativeBuilder().build_time_horizon_explanation(evidence)
    assert "short-term" in text
    assert "ADX" not in text
