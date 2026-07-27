"""Unit tests for src.analysis.indicators.fibonacci."""

import pandas as pd
import pytest

from src.analysis.indicators.fibonacci import fibonacci_retracement_levels


def _make_df(highs, lows):
    n = len(highs)
    return pd.DataFrame(
        {
            "open": highs,
            "high": highs,
            "low": lows,
            "close": highs,
            "volume": [1000.0] * n,
        }
    )


def test_uptrend_levels_are_measured_down_from_the_high():
    # Low at index 0, high at index 4 -- low preceded high -> uptrend.
    df = _make_df(highs=[100, 100, 100, 100, 200], lows=[50, 60, 70, 80, 90])
    result = fibonacci_retracement_levels(df)

    assert result.is_uptrend is True
    assert result.swing_high == 200
    assert result.swing_low == 50
    assert result.levels["0.0"] == pytest.approx(200)
    assert result.levels["100.0"] == pytest.approx(50)
    assert result.levels["50.0"] == pytest.approx(125)
    assert result.levels["61.8"] == pytest.approx(200 - 150 * 0.618)


def test_downtrend_levels_are_measured_up_from_the_low():
    # High at index 0, low at index 4 -- high preceded low -> downtrend.
    df = _make_df(highs=[200, 150, 140, 130, 100], lows=[90, 80, 70, 60, 50])
    result = fibonacci_retracement_levels(df)

    assert result.is_uptrend is False
    assert result.levels["0.0"] == pytest.approx(50)
    assert result.levels["100.0"] == pytest.approx(200)
    assert result.levels["50.0"] == pytest.approx(125)


def test_lookback_restricts_the_analyzed_window():
    # Without a lookback, the huge early spike dominates; with lookback=3
    # only the last 3 (flat, low-range) bars are considered.
    df = _make_df(highs=[1000, 100, 100, 100], lows=[10, 90, 90, 90])
    full = fibonacci_retracement_levels(df)
    windowed = fibonacci_retracement_levels(df, lookback=3)

    assert full.swing_high == 1000
    assert windowed.swing_high == 100
    assert windowed.swing_low == 90


def test_insufficient_data_raises():
    df = _make_df(highs=[100], lows=[90])
    with pytest.raises(ValueError):
        fibonacci_retracement_levels(df)
