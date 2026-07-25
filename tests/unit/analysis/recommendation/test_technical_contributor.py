"""Unit tests for TechnicalScoreContributor.

Builds TechnicalAnalysisResult directly from hand-picked IndicatorOutput
values (rather than running TechnicalAnalysisEngine over synthetic
OHLCV) so each rule can be exercised deterministically and in
isolation -- e.g. "RSI is exactly 71" -- without depending on how a
particular price series happens to make RSI/MACD/etc. come out.
"""

import pandas as pd
import pytest

from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor
from src.analysis.recommendation.types import AnalysisContext, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import (
    BollingerBandsResult,
    IndicatorCategory,
    IndicatorOutput,
    MACDResult,
    PatternMatch,
    SuperTrendResult,
)


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _flat_series(value, n=15):
    return pd.Series([value] * n)


def _default_indicators(**overrides):
    indicators = {
        "rsi_14": _output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([50.0])),
        "macd": _output(
            "macd",
            IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([0.0]), signal_line=pd.Series([0.0]), histogram=pd.Series([0.0])),
        ),
        "supertrend": _output(
            "supertrend",
            IndicatorCategory.TREND,
            SuperTrendResult(trend=pd.Series([0.0]), direction=pd.Series([0.0])),
        ),
        "sma_20": _output("sma_20", IndicatorCategory.TREND, pd.Series([100.0])),
        "ema_20": _output("ema_20", IndicatorCategory.TREND, pd.Series([100.0])),
        "adx_14": _output("adx_14", IndicatorCategory.TREND, pd.Series([20.0])),
        "atr_14": _output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([1.0])),
        "obv": _output("obv", IndicatorCategory.VOLUME, _flat_series(1000.0)),
        "volume_sma_20": _output("volume_sma_20", IndicatorCategory.VOLUME, _flat_series(1000.0)),
        "bollinger": _output(
            "bollinger",
            IndicatorCategory.VOLATILITY,
            BollingerBandsResult(upper=_flat_series(110.0), middle=_flat_series(100.0), lower=_flat_series(90.0)),
        ),
        "candlestick_patterns": _output("candlestick_patterns", IndicatorCategory.PRICE_ACTION, []),
    }
    indicators.update(overrides)
    return TechnicalAnalysisResult(indicators=indicators)


def _contribute(result):
    contributor = TechnicalScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=result)
    return contributor.contribute(context)


# --- unavailable ---------------------------------------------------------


def test_no_technical_result_is_reported_as_unavailable():
    contributor = TechnicalScoreContributor()
    context = AnalysisContext(symbol="2222", technical_result=None)

    contribution = contributor.contribute(context)

    assert contribution.source == "technical"
    assert contribution.score is None
    assert contribution.weight == 0.0
    assert contribution.confidence == 0.0
    assert contribution.signals == []
    assert "No technical analysis" in contribution.notes


# --- RSI -------------------------------------------------------------------


def test_rsi_oversold_is_bullish():
    result = _default_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([22.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_14")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 15.0


def test_rsi_overbought_is_bearish():
    result = _default_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([88.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_14")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -15.0


def test_rsi_above_50_is_mildly_bullish():
    result = _default_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([60.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_14")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 6.0


def test_rsi_below_50_is_mildly_bearish():
    result = _default_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([40.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_14")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_rsi_exactly_50_is_neutral():
    result = _default_indicators(rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([50.0])))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "rsi_14")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 0.0


# --- MACD --------------------------------------------------------------


def test_macd_bullish_crossover():
    result = _default_indicators(
        macd=_output(
            "macd",
            IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([1.0]), signal_line=pd.Series([0.5]), histogram=pd.Series([0.5])),
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "macd")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 12.0


def test_macd_bearish_crossover():
    result = _default_indicators(
        macd=_output(
            "macd",
            IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([-1.0]), signal_line=pd.Series([-0.5]), histogram=pd.Series([-0.5])),
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "macd")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -12.0


def test_macd_missing_is_skipped_not_errored():
    result = _default_indicators(
        macd=_output(
            "macd",
            IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([float("nan")]), signal_line=pd.Series([float("nan")]), histogram=pd.Series([float("nan")])),
        )
    )
    contribution = _contribute(result)
    assert not any(s.name == "macd" for s in contribution.signals)
    assert contribution.score is not None  # the rest of the signals still compute


# --- Supertrend ----------------------------------------------------------


def test_supertrend_bullish():
    result = _default_indicators(
        supertrend=_output(
            "supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([1.0]))
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "supertrend")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_supertrend_bearish():
    result = _default_indicators(
        supertrend=_output(
            "supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([-1.0]))
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "supertrend")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -10.0


# --- EMA vs SMA ------------------------------------------------------------


def test_ema_above_sma_is_bullish():
    result = _default_indicators(
        ema_20=_output("ema_20", IndicatorCategory.TREND, pd.Series([105.0])),
        sma_20=_output("sma_20", IndicatorCategory.TREND, pd.Series([100.0])),
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "ema_vs_sma")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 8.0


def test_ema_below_sma_is_bearish():
    result = _default_indicators(
        ema_20=_output("ema_20", IndicatorCategory.TREND, pd.Series([95.0])),
        sma_20=_output("sma_20", IndicatorCategory.TREND, pd.Series([100.0])),
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "ema_vs_sma")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


# --- OBV / volume trend ------------------------------------------------


def test_obv_rising_is_bullish():
    result = _default_indicators(obv=_output("obv", IndicatorCategory.VOLUME, pd.Series(list(range(0, 220, 20)))))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "obv")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 6.0


def test_obv_falling_is_bearish():
    result = _default_indicators(obv=_output("obv", IndicatorCategory.VOLUME, pd.Series(list(range(220, 0, -20)))))
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "obv")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_obv_insufficient_history_is_skipped():
    result = _default_indicators(obv=_output("obv", IndicatorCategory.VOLUME, pd.Series([100.0])))
    contribution = _contribute(result)
    assert not any(s.name == "obv" for s in contribution.signals)


def test_volume_trend_rising_is_bullish():
    result = _default_indicators(
        volume_sma_20=_output("volume_sma_20", IndicatorCategory.VOLUME, pd.Series([1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0]))
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "volume_sma_20")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 4.0


# --- Candlestick patterns -----------------------------------------------


def test_bullish_pattern_adds_points():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = _default_indicators(
        candlestick_patterns=_output(
            "candlestick_patterns",
            IndicatorCategory.PRICE_ACTION,
            [PatternMatch(pattern_name="hammer", timestamp=now, bullish=True)],
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "pattern:hammer")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 6.0


def test_bearish_pattern_subtracts_points():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = _default_indicators(
        candlestick_patterns=_output(
            "candlestick_patterns",
            IndicatorCategory.PRICE_ACTION,
            [PatternMatch(pattern_name="shooting_star", timestamp=now, bullish=False)],
        )
    )
    contribution = _contribute(result)
    sig = next(s for s in contribution.signals if s.name == "pattern:shooting_star")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_many_patterns_are_capped_not_unbounded():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    matches = [PatternMatch(pattern_name=f"pattern_{i}", timestamp=now, bullish=True) for i in range(10)]
    result = _default_indicators(candlestick_patterns=_output("candlestick_patterns", IndicatorCategory.PRICE_ACTION, matches))
    contribution = _contribute(result)
    pattern_signals = [s for s in contribution.signals if s.name.startswith("pattern:")]
    assert sum(s.impact for s in pattern_signals) == 12.0  # capped, not 10 * 6.0 = 60.0


def test_only_latest_timestamp_patterns_count():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = _default_indicators(
        candlestick_patterns=_output(
            "candlestick_patterns",
            IndicatorCategory.PRICE_ACTION,
            [
                PatternMatch(pattern_name="old_pattern", timestamp=now - timedelta(days=5), bullish=False),
                PatternMatch(pattern_name="new_pattern", timestamp=now, bullish=True),
            ],
        )
    )
    contribution = _contribute(result)
    pattern_signals = [s for s in contribution.signals if s.name.startswith("pattern:")]
    assert len(pattern_signals) == 1
    assert pattern_signals[0].name == "pattern:new_pattern"


# --- Bollinger width (informational only) --------------------------------


def test_bollinger_widening_is_a_zero_impact_signal():
    upper = pd.Series([105.0] * 10 + [130.0])
    lower = pd.Series([95.0] * 10 + [70.0])
    middle = pd.Series([100.0] * 11)
    result = _default_indicators(
        bollinger=_output("bollinger", IndicatorCategory.VOLATILITY, BollingerBandsResult(upper=upper, middle=middle, lower=lower))
    )
    contribution = _contribute(result)
    sig = next((s for s in contribution.signals if s.name == "bollinger_width"), None)
    assert sig is not None
    assert sig.impact == 0.0
    assert "widening" in sig.description


# --- ADX confidence adjustment -------------------------------------------


def test_strong_trend_adx_boosts_confidence():
    weak = _default_indicators(adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([10.0])))
    strong = _default_indicators(adx_14=_output("adx_14", IndicatorCategory.TREND, pd.Series([30.0])))

    weak_confidence = _contribute(weak).confidence
    strong_confidence = _contribute(strong).confidence

    assert strong_confidence > weak_confidence


# --- Aggregate behavior --------------------------------------------------


def test_score_is_clamped_to_0_100_under_maximal_bullish_signals():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = _default_indicators(
        rsi_14=_output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([20.0])),
        macd=_output(
            "macd", IndicatorCategory.MOMENTUM,
            MACDResult(macd_line=pd.Series([2.0]), signal_line=pd.Series([1.0]), histogram=pd.Series([1.0])),
        ),
        supertrend=_output("supertrend", IndicatorCategory.TREND, SuperTrendResult(trend=pd.Series([1.0]), direction=pd.Series([1.0]))),
        ema_20=_output("ema_20", IndicatorCategory.TREND, pd.Series([110.0])),
        sma_20=_output("sma_20", IndicatorCategory.TREND, pd.Series([100.0])),
        obv=_output("obv", IndicatorCategory.VOLUME, pd.Series(list(range(0, 300, 20)))),
        volume_sma_20=_output("volume_sma_20", IndicatorCategory.VOLUME, pd.Series([1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3500.0])),
        candlestick_patterns=_output(
            "candlestick_patterns", IndicatorCategory.PRICE_ACTION,
            [PatternMatch(pattern_name=f"p{i}", timestamp=now, bullish=True) for i in range(5)],
        ),
    )
    contribution = _contribute(result)
    assert contribution.score == 100.0


def test_full_contribution_has_full_confidence_when_every_core_signal_computes():
    contribution = _contribute(_default_indicators())
    assert contribution.confidence == 100.0
    assert contribution.weight == 0.5
    assert contribution.score == 50.0  # every default value is exactly neutral


def test_default_weight_is_configurable():
    contributor = TechnicalScoreContributor(weight=0.7)
    context = AnalysisContext(symbol="2222", technical_result=_default_indicators())
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.7
