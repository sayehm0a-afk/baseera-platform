"""Unit tests for VolumeScoreContributor."""

import pandas as pd

from src.analysis.decision.contributors.volume_contributor import VolumeScoreContributor
from src.analysis.recommendation.types import AnalysisContext, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import IndicatorCategory, IndicatorOutput


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _base_indicators(**overrides):
    indicators = {
        "obv": _output("obv", IndicatorCategory.VOLUME, pd.Series([1000.0] * 11)),
        "volume_sma_20": _output("volume_sma_20", IndicatorCategory.VOLUME, pd.Series([1000.0] * 11)),
    }
    indicators.update(overrides)
    return TechnicalAnalysisResult(indicators=indicators)


def _contribute(result):
    contributor = VolumeScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=result)
    return contributor.contribute(context)


def test_no_technical_result_is_unavailable():
    contributor = VolumeScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=None)
    contribution = contributor.contribute(context)
    assert contribution.source == "volume"
    assert contribution.score is None
    assert contribution.weight == 0.0


# --- OBV acceleration ----------------------------------------------------


def test_obv_flow_accelerating_up_is_bullish():
    obv = pd.Series([0.0, 10, 20, 30, 40, 50, 60, 80, 100, 120, 150])
    result = _base_indicators(obv=_output("obv", IndicatorCategory.VOLUME, obv))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "obv_acceleration")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_obv_flow_accelerating_down_is_bearish():
    obv = pd.Series([0.0, -10, -20, -30, -40, -50, -60, -80, -100, -120, -150])
    result = _base_indicators(obv=_output("obv", IndicatorCategory.VOLUME, obv))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "obv_acceleration")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -10.0


def test_obv_flat_is_neutral():
    result = _base_indicators()
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "obv_acceleration")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


def test_obv_insufficient_history_is_skipped():
    result = _base_indicators(obv=_output("obv", IndicatorCategory.VOLUME, pd.Series([1000.0] * 5)))
    contribution = _contribute(result)
    assert not any(s.name == "obv_acceleration" for s in contribution.signals)


# --- Volume surge ----------------------------------------------------


def test_volume_surge_above_baseline_is_bullish():
    volume_sma = pd.Series([1000.0] * 10 + [1300.0])
    result = _base_indicators(volume_sma_20=_output("volume_sma_20", IndicatorCategory.VOLUME, volume_sma))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "volume_surge")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 8.0


def test_volume_below_baseline_is_bearish():
    volume_sma = pd.Series([1000.0] * 10 + [700.0])
    result = _base_indicators(volume_sma_20=_output("volume_sma_20", IndicatorCategory.VOLUME, volume_sma))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "volume_surge")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


def test_volume_close_to_baseline_is_neutral():
    volume_sma = pd.Series([1000.0] * 10 + [1050.0])
    result = _base_indicators(volume_sma_20=_output("volume_sma_20", IndicatorCategory.VOLUME, volume_sma))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "volume_surge")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


def test_volume_surge_insufficient_history_is_skipped():
    result = _base_indicators(volume_sma_20=_output("volume_sma_20", IndicatorCategory.VOLUME, pd.Series([1000.0] * 5)))
    contribution = _contribute(result)
    assert not any(s.name == "volume_surge" for s in contribution.signals)


# --- Aggregate -------------------------------------------------------


def test_default_indicators_yield_neutral_score_and_full_confidence():
    contribution = _contribute(_base_indicators())
    assert contribution.score == 50.0
    assert contribution.confidence == 100.0
    assert contribution.weight == 0.10


def test_default_weight_is_configurable():
    contributor = VolumeScoreContributor(weight=0.2)
    context = AnalysisContext(symbol="2222", technical_result=_base_indicators())
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.2
