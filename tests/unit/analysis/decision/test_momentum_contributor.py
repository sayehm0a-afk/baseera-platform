"""Unit tests for MomentumScoreContributor.

Builds TechnicalAnalysisResult directly from hand-picked IndicatorOutput
series (same approach as test_technical_contributor.py) so each rule
is exercised deterministically.
"""

import pandas as pd

from src.analysis.decision.contributors.momentum_contributor import MomentumScoreContributor
from src.analysis.recommendation.types import AnalysisContext, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import IndicatorCategory, IndicatorOutput, MACDResult, SuperTrendResult


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _base_indicators(**overrides):
    indicators = {
        "rsi_14": _output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([50.0] * 11)),
        "macd": _output(
            "macd", IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([0.0] * 11), signal_line=pd.Series([0.0] * 11), histogram=pd.Series([0.0] * 11)),
        ),
        "supertrend": _output(
            "supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([0.0]), direction=pd.Series([0.0]))
        ),
        "adx_14": _output("adx_14", IndicatorCategory.TREND, pd.Series([20.0])),
    }
    indicators.update(overrides)
    return TechnicalAnalysisResult(indicators=indicators)


def _contribute(result, latest_price=None):
    contributor = MomentumScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=result, latest_price=latest_price)
    return contributor.contribute(context)


def test_no_technical_result_is_unavailable():
    contributor = MomentumScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=None)
    contribution = contributor.contribute(context)
    assert contribution.source == "momentum"
    assert contribution.score is None
    assert contribution.weight == 0.0


# --- RSI velocity -----------------------------------------------------


def test_rsi_rising_is_bullish():
    result = _base_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([45.0, 46, 47, 48, 49, 60.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_velocity")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_rsi_falling_is_bearish():
    result = _base_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([60.0, 58, 56, 54, 52, 45.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_velocity")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -10.0


def test_rsi_flat_is_neutral():
    result = _base_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([50.0] * 6)))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_velocity")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


def test_rsi_insufficient_history_is_skipped():
    result = _base_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([50.0])))
    contribution = _contribute(result)
    assert not any(s.name == "rsi_velocity" for s in contribution.signals)


# --- MACD histogram acceleration ---------------------------------------


def test_macd_histogram_expanding_positively_is_bullish():
    histogram = pd.Series([0.1, 0.1, 0.1, 0.1, 0.1, 0.5])
    result = _base_indicators(
        macd=_output(
            "macd", IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([0.0] * 6), signal_line=pd.Series([0.0] * 6), histogram=histogram),
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "macd_acceleration")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_macd_histogram_expanding_negatively_is_bearish():
    histogram = pd.Series([-0.1, -0.1, -0.1, -0.1, -0.1, -0.5])
    result = _base_indicators(
        macd=_output(
            "macd", IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([0.0] * 6), signal_line=pd.Series([0.0] * 6), histogram=histogram),
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "macd_acceleration")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -10.0


def test_macd_histogram_crossing_zero_is_neutral():
    histogram = pd.Series([-0.5, -0.4, -0.3, -0.2, -0.15, -0.1])
    result = _base_indicators(
        macd=_output(
            "macd", IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([0.0] * 6), signal_line=pd.Series([0.0] * 6), histogram=histogram),
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "macd_acceleration")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


# --- Trend strength (ADX + Supertrend direction) --------------------------


def test_strong_trend_bullish_direction():
    result = _base_indicators(
        adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([30.0])),
        supertrend=_output("supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([1.0]))),
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "trend_strength")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_strong_trend_bearish_direction():
    result = _base_indicators(
        adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([30.0])),
        supertrend=_output("supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([-1.0]))),
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "trend_strength")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -10.0


def test_weak_trend_is_neutral_regardless_of_direction():
    result = _base_indicators(
        adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([10.0])),
        supertrend=_output("supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([1.0]))),
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "trend_strength")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


def test_moderate_trend_scales_down_the_points():
    result = _base_indicators(
        adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([20.0])),
        supertrend=_output("supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([1.0]))),
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "trend_strength")
    assert sig.impact == 5.0


def test_trend_strength_missing_adx_is_skipped():
    result = _base_indicators(adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([float("nan")])))
    contribution = _contribute(result)
    assert not any(s.name == "trend_strength" for s in contribution.signals)


# --- Aggregate -------------------------------------------------------


def test_default_indicators_yield_neutral_score_and_full_confidence():
    contribution = _contribute(_base_indicators())
    assert contribution.score == 50.0
    assert contribution.confidence == 100.0
    assert contribution.weight == 0.15


def test_default_weight_is_configurable():
    contributor = MomentumScoreContributor(weight=0.3)
    context = AnalysisContext(symbol="2222", technical_result=_base_indicators())
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.3
