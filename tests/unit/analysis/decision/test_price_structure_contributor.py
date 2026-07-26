"""Unit tests for PriceStructureScoreContributor (Fibonacci +
support/resistance)."""

import pandas as pd

from src.analysis.decision.contributors.price_structure_contributor import (
    PriceStructureScoreContributor,
)
from src.analysis.recommendation.types import AnalysisContext, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import (
    BollingerBandsResult,
    FibonacciLevels,
    IndicatorCategory,
    IndicatorOutput,
    SupportResistanceLevels,
)


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _base_indicators(support=None, resistance=None, fib_levels=None, is_uptrend=True, **overrides):
    indicators = {
        "bollinger": _output(
            "bollinger", IndicatorCategory.VOLATILITY,
            BollingerBandsResult(upper=pd.Series([103.5]), middle=pd.Series([100.0]), lower=pd.Series([96.5])),
        ),
        "support_resistance": _output(
            "support_resistance", IndicatorCategory.PRICE_ACTION,
            SupportResistanceLevels(support=support or [], resistance=resistance or []),
        ),
        "fibonacci_retracement": _output(
            "fibonacci_retracement", IndicatorCategory.PRICE_ACTION,
            FibonacciLevels(
                swing_high=110.0, swing_high_at=1, swing_low=90.0, swing_low_at=0,
                is_uptrend=is_uptrend, levels=fib_levels or {},
            ),
        ),
    }
    indicators.update(overrides)
    return TechnicalAnalysisResult(indicators=indicators)


def _contribute(result, latest_price=None):
    contributor = PriceStructureScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=result, latest_price=latest_price)
    return contributor.contribute(context)


def test_no_technical_result_is_unavailable():
    contributor = PriceStructureScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=None)
    contribution = contributor.contribute(context)
    assert contribution.source == "price_structure"
    assert contribution.score is None
    assert contribution.weight == 0.0


# --- resistance proximity --------------------------------------------------


def test_near_resistance_is_bearish():
    result = _base_indicators(resistance=[101.0])  # 1% above price=100.0
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "resistance_proximity")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


def test_far_from_resistance_is_neutral():
    result = _base_indicators(resistance=[150.0])
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "resistance_proximity")
    assert sig.direction == SignalDirection.NEUTRAL


def test_price_above_all_resistance_is_a_bullish_breakout():
    result = _base_indicators(resistance=[95.0])  # below price -- already broken
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "resistance_breakout")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 8.0


def test_no_resistance_levels_skips_the_signal():
    result = _base_indicators(resistance=[])
    contribution = _contribute(result, latest_price=100.0)
    assert not any(s.name in ("resistance_proximity", "resistance_breakout") for s in contribution.signals)


# --- support proximity -------------------------------------------------


def test_near_support_is_bullish():
    result = _base_indicators(support=[99.0])  # 1% below price=100.0
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "support_proximity")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 8.0


def test_far_from_support_is_neutral():
    result = _base_indicators(support=[50.0])
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "support_proximity")
    assert sig.direction == SignalDirection.NEUTRAL


def test_price_below_all_support_is_a_bearish_breakdown():
    result = _base_indicators(support=[105.0])  # above price -- already broken down
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "support_breakdown")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


# --- fibonacci proximity -------------------------------------------------


def test_near_fibonacci_level_in_an_uptrend_is_bullish():
    result = _base_indicators(fib_levels={"61.8": 100.5}, is_uptrend=True)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "fibonacci_proximity")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 6.0


def test_near_fibonacci_level_in_a_downtrend_is_bearish():
    result = _base_indicators(fib_levels={"61.8": 100.5}, is_uptrend=False)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "fibonacci_proximity")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_far_from_any_fibonacci_level_is_neutral():
    result = _base_indicators(fib_levels={"61.8": 200.0}, is_uptrend=True)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "fibonacci_proximity")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


# --- price fallback ------------------------------------------------------


def test_uses_bollinger_middle_as_price_fallback_when_no_live_price():
    result = _base_indicators(resistance=[100.5])  # ~0.5% above Bollinger middle=100.0
    contribution = _contribute(result, latest_price=None)
    sig = next(s for s in contribution.signals if s.name == "resistance_proximity")
    assert sig.direction == SignalDirection.BEARISH


# --- aggregate -----------------------------------------------------------


def test_default_weight_is_configurable():
    contributor = PriceStructureScoreContributor(weight=0.3)
    context = AnalysisContext(symbol="2222", technical_result=_base_indicators(), latest_price=100.0)
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.3


def test_full_confidence_when_all_three_signals_compute():
    result = _base_indicators(support=[80.0], resistance=[150.0], fib_levels={"50.0": 100.5})
    contribution = _contribute(result, latest_price=100.0)
    assert contribution.confidence == 100.0
