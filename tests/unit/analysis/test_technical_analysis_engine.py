"""Integration tests for TechnicalAnalysisEngine / TechnicalAnalysisResult
and the registry-based extension point they are built on.

These tests deliberately exercise the architectural requirement behind
M2.2's design: a future consumer (Composite Indicator Engine, Signal
Engine, etc.) must be able to add or discover indicators generically,
through `IndicatorRegistry`/`IndicatorOutput`, without any change to
`TechnicalAnalysisEngine` itself.
"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.registry import DEFAULT_REGISTRY, IndicatorRegistry, IndicatorSpec
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.analysis.types import IndicatorCategory, IndicatorOutput


def _make_ohlcv(n=60, seed=42):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0, 1, n))
    low = close - np.abs(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(10000, 100000, n).astype(float)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )
    df.index.name = "timestamp"
    return df


EXPECTED_DEFAULT_INDICATOR_NAMES = {
    "sma_20",
    "ema_20",
    "adx_14",
    "supertrend",
    "rsi_14",
    "macd",
    "bollinger",
    "atr_14",
    "obv",
    "volume_sma_20",
    "candlestick_patterns",
}


def test_analyze_computes_every_default_indicator():
    engine = TechnicalAnalysisEngine()
    result = engine.analyze(_make_ohlcv())

    assert set(result.indicators.keys()) == EXPECTED_DEFAULT_INDICATOR_NAMES
    for name, output in result.indicators.items():
        assert isinstance(output, IndicatorOutput)
        assert output.name == name


def test_analyze_typed_properties_match_indicators_dict():
    engine = TechnicalAnalysisEngine()
    result = engine.analyze(_make_ohlcv())

    assert result.sma_20 is result.indicators["sma_20"].value
    assert result.rsi_14 is result.indicators["rsi_14"].value
    assert result.macd is result.indicators["macd"].value
    assert result.bollinger is result.indicators["bollinger"].value
    assert result.supertrend is result.indicators["supertrend"].value
    assert result.patterns is result.indicators["candlestick_patterns"].value


def test_latest_snapshot_has_one_entry_per_indicator_with_no_exceptions():
    engine = TechnicalAnalysisEngine()
    result = engine.analyze(_make_ohlcv())

    snapshot = result.latest_snapshot()

    assert set(snapshot.keys()) == EXPECTED_DEFAULT_INDICATOR_NAMES
    # sma_20/rsi_14/atr_14 etc. resolve to a plain float latest value
    assert isinstance(snapshot["sma_20"], float)
    # composite indicators resolve to a dict of their sub-series' latest values
    assert set(snapshot["macd"].keys()) == {"macd_line", "signal_line", "histogram"}
    assert set(snapshot["bollinger"].keys()) == {"upper", "middle", "lower"}
    assert set(snapshot["supertrend"].keys()) == {"trend", "direction"}
    # candlestick_patterns resolves to a list of pattern names at the latest bar
    assert isinstance(snapshot["candlestick_patterns"], list)


def test_get_raises_key_error_for_unknown_indicator():
    engine = TechnicalAnalysisEngine()
    result = engine.analyze(_make_ohlcv())

    with pytest.raises(KeyError):
        result.get("does_not_exist")


def test_analyze_missing_column_raises():
    df = _make_ohlcv().drop(columns=["volume"])
    engine = TechnicalAnalysisEngine()

    with pytest.raises(ValueError, match="volume"):
        engine.analyze(df)


def test_analyze_insufficient_rows_raises():
    df = _make_ohlcv(n=20)
    engine = TechnicalAnalysisEngine()

    with pytest.raises(ValueError, match="35"):
        engine.analyze(df)


# ---------------------------------------------------------------------------
# Extension point: a registry-driven, forward-looking consumer should be
# able to add a brand-new "indicator" without TechnicalAnalysisEngine or
# any existing indicator changing at all.
# ---------------------------------------------------------------------------


def test_engine_works_with_a_custom_registry_extension():
    registry = IndicatorRegistry()
    registry.register(
        IndicatorSpec(
            "future_smart_money_placeholder",
            IndicatorCategory.TREND,
            lambda df: pd.Series([42.0] * len(df), index=df.index),
        )
    )

    engine = TechnicalAnalysisEngine(registry=registry)
    result = engine.analyze(_make_ohlcv())

    assert set(result.indicators.keys()) == {"future_smart_money_placeholder"}
    assert result.get("future_smart_money_placeholder").latest() == 42.0


def test_engine_default_registry_is_unaffected_by_custom_registries():
    # Building/using a separate registry must never mutate DEFAULT_REGISTRY.
    before = {spec.name for spec in DEFAULT_REGISTRY.all_specs()}

    custom = IndicatorRegistry()
    custom.register(IndicatorSpec("temp", IndicatorCategory.TREND, lambda df: df["close"]))

    after = {spec.name for spec in DEFAULT_REGISTRY.all_specs()}
    assert before == after
    assert "temp" not in after


def test_registry_rejects_duplicate_indicator_names():
    registry = IndicatorRegistry()
    registry.register(IndicatorSpec("dup", IndicatorCategory.TREND, lambda df: df["close"]))

    with pytest.raises(ValueError, match="dup"):
        registry.register(IndicatorSpec("dup", IndicatorCategory.MOMENTUM, lambda df: df["close"]))


def test_default_registry_has_exactly_the_m22_indicator_set():
    names = {spec.name for spec in DEFAULT_REGISTRY.all_specs()}
    assert names == EXPECTED_DEFAULT_INDICATOR_NAMES
