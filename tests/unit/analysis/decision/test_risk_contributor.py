"""Unit tests for RiskScoreContributor.

Recall the sign convention (documented in risk_contributor.py):
positive points = *low* risk (favorable), negative points = elevated
risk (unfavorable) -- the mirror of every other contributor.
"""

import pandas as pd

from src.analysis.decision.contributors.risk_contributor import RiskScoreContributor
from src.analysis.recommendation.types import AnalysisContext, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import BollingerBandsResult, IndicatorCategory, IndicatorOutput


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _base_indicators(**overrides):
    indicators = {
        "atr_14": _output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([2.0])),
        "bollinger": _output(
            "bollinger", IndicatorCategory.VOLATILITY,
            BollingerBandsResult(upper=pd.Series([103.5]), middle=pd.Series([100.0]), lower=pd.Series([96.5])),
        ),
    }
    indicators.update(overrides)
    return TechnicalAnalysisResult(indicators=indicators)


def _contribute(result, latest_price=None):
    contributor = RiskScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=result, latest_price=latest_price)
    return contributor.contribute(context)


def test_no_technical_result_is_unavailable():
    contributor = RiskScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=None)
    contribution = contributor.contribute(context)
    assert contribution.source == "risk"
    assert contribution.score is None
    assert contribution.weight == 0.0


# --- ATR volatility ratio -------------------------------------------


def test_elevated_atr_ratio_is_bearish_high_risk():
    result = _base_indicators(atr_14=_output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([3.5])))
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "atr_volatility")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


def test_low_atr_ratio_is_bullish_low_risk():
    result = _base_indicators(atr_14=_output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([1.0])))
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "atr_volatility")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 4.0


def test_moderate_atr_ratio_is_neutral():
    result = _base_indicators(atr_14=_output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([2.0])))
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "atr_volatility")
    assert sig.direction == SignalDirection.NEUTRAL


def test_uses_bollinger_middle_as_price_fallback_when_no_live_price():
    # ATR=3.5 against bollinger middle=100.0 -> ratio 0.035, elevated.
    result = _base_indicators(atr_14=_output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([3.5])))
    contribution = _contribute(result, latest_price=None)
    sig = next(s for s in contribution.signals if s.name == "atr_volatility")
    assert sig.direction == SignalDirection.BEARISH


def test_atr_ratio_skipped_when_atr_missing():
    result = _base_indicators(atr_14=_output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([float("nan")])))
    contribution = _contribute(result, latest_price=100.0)
    assert not any(s.name == "atr_volatility" for s in contribution.signals)


# --- Bollinger Band width -----------------------------------------------


def test_wide_bands_are_bearish_high_risk():
    result = _base_indicators(
        bollinger=_output(
            "bollinger", IndicatorCategory.VOLATILITY,
            BollingerBandsResult(upper=pd.Series([112.0]), middle=pd.Series([100.0]), lower=pd.Series([88.0])),
        )
    )
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "bollinger_band_risk")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_narrow_bands_are_bullish_low_risk():
    result = _base_indicators(
        bollinger=_output(
            "bollinger", IndicatorCategory.VOLATILITY,
            BollingerBandsResult(upper=pd.Series([102.0]), middle=pd.Series([100.0]), lower=pd.Series([98.0])),
        )
    )
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "bollinger_band_risk")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 3.0


def test_moderate_band_width_is_neutral():
    contribution = _contribute(_base_indicators(), latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "bollinger_band_risk")
    assert sig.direction == SignalDirection.NEUTRAL


# --- Aggregate -------------------------------------------------------


def test_default_indicators_yield_neutral_score_and_full_confidence():
    contribution = _contribute(_base_indicators(), latest_price=100.0)
    assert contribution.score == 50.0
    assert contribution.confidence == 100.0
    assert contribution.weight == 0.10


def test_default_weight_is_configurable():
    contributor = RiskScoreContributor(weight=0.25)
    context = AnalysisContext(symbol="2222", technical_result=_base_indicators(), latest_price=100.0)
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.25
