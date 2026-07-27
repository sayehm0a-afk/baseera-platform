"""Unit tests for ValueAreaScoreContributor (VWAP + Volume Profile)."""

import pandas as pd

from src.analysis.decision.contributors.value_area_contributor import ValueAreaScoreContributor
from src.analysis.recommendation.types import AnalysisContext, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import BollingerBandsResult, IndicatorCategory, IndicatorOutput, VolumeProfileResult


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _base_indicators(vwap=100.0, poc=100.0, **overrides):
    indicators = {
        "bollinger": _output(
            "bollinger", IndicatorCategory.VOLATILITY,
            BollingerBandsResult(upper=pd.Series([103.5]), middle=pd.Series([100.0]), lower=pd.Series([96.5])),
        ),
        "vwap_20": _output("vwap_20", IndicatorCategory.VOLUME, pd.Series([vwap])),
        "volume_profile": _output(
            "volume_profile", IndicatorCategory.VOLUME,
            VolumeProfileResult(bin_edges=[90.0, 100.0, 110.0], bin_volumes=[100.0, 500.0, 100.0], point_of_control=poc),
        ),
    }
    indicators.update(overrides)
    return TechnicalAnalysisResult(indicators=indicators)


def _contribute(result, latest_price=None):
    contributor = ValueAreaScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=result, latest_price=latest_price)
    return contributor.contribute(context)


def test_no_technical_result_is_unavailable():
    contributor = ValueAreaScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=None)
    contribution = contributor.contribute(context)
    assert contribution.source == "value_area"
    assert contribution.score is None
    assert contribution.weight == 0.0


# --- VWAP ------------------------------------------------------------------


def test_price_above_vwap_is_bullish():
    result = _base_indicators(vwap=98.0)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "vwap_deviation")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 6.0


def test_price_below_vwap_is_bearish():
    result = _base_indicators(vwap=102.0)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "vwap_deviation")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_price_close_to_vwap_is_neutral():
    result = _base_indicators(vwap=100.05)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "vwap_deviation")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


def test_vwap_missing_is_skipped():
    result = _base_indicators(vwap_20=_output("vwap_20", IndicatorCategory.VOLUME, pd.Series([float("nan")])))
    contribution = _contribute(result, latest_price=100.0)
    assert not any(s.name == "vwap_deviation" for s in contribution.signals)


# --- Volume Profile point of control --------------------------------------


def test_price_above_poc_is_bullish():
    result = _base_indicators(poc=95.0)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "volume_profile_deviation")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 5.0


def test_price_below_poc_is_bearish():
    result = _base_indicators(poc=105.0)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "volume_profile_deviation")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -5.0


def test_price_close_to_poc_is_neutral():
    result = _base_indicators(poc=100.1)
    contribution = _contribute(result, latest_price=100.0)
    sig = next(s for s in contribution.signals if s.name == "volume_profile_deviation")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


# --- price fallback / aggregate --------------------------------------------


def test_uses_bollinger_middle_as_price_fallback_when_no_live_price():
    result = _base_indicators(vwap=95.0)  # bollinger middle=100.0 -> 5% above VWAP
    contribution = _contribute(result, latest_price=None)
    sig = next(s for s in contribution.signals if s.name == "vwap_deviation")
    assert sig.direction == SignalDirection.BULLISH


def test_default_weight_is_configurable():
    contributor = ValueAreaScoreContributor(weight=0.3)
    context = AnalysisContext(symbol="2222", technical_result=_base_indicators(), latest_price=100.0)
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.3


def test_full_confidence_when_both_signals_compute():
    contribution = _contribute(_base_indicators(), latest_price=100.0)
    assert contribution.confidence == 100.0
