"""Unit tests for src.analysis.indicators.support_resistance."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators.support_resistance import support_resistance_levels


def _make_df(highs, lows):
    n = len(highs)
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * n,
        }
    )


def test_detects_an_obvious_single_resistance_pivot():
    # A single sharp spike at index 5, flanked symmetrically by lower
    # values on both sides -- an unambiguous resistance pivot.
    highs = [100, 101, 102, 103, 104, 150, 104, 103, 102, 101, 100]
    lows = [h - 5 for h in highs]
    df = _make_df(highs, lows)

    result = support_resistance_levels(df, order=5)
    assert 150.0 in result.resistance


def test_detects_an_obvious_single_support_pivot():
    lows = [100, 99, 98, 97, 96, 50, 96, 97, 98, 99, 100]
    highs = [low + 5 for low in lows]
    df = _make_df(highs, lows)

    result = support_resistance_levels(df, order=5)
    assert 50.0 in result.support


def test_monotonic_series_has_no_pivots():
    # A strictly increasing series never has an interior bar that is
    # simultaneously higher than everything before AND after it.
    n = 21
    highs = np.arange(n, dtype="float64") + 100
    lows = highs - 5
    df = _make_df(highs.tolist(), lows.tolist())

    result = support_resistance_levels(df, order=5)
    assert result.resistance == []
    assert result.support == []


def test_levels_are_sorted_and_deduplicated():
    highs = [100, 101, 102, 103, 104, 150, 104, 103, 102, 101, 100, 99, 98, 97, 96, 150, 96, 97, 98, 99, 100]
    lows = [h - 5 for h in highs]
    df = _make_df(highs, lows)

    result = support_resistance_levels(df, order=5)
    assert result.resistance == sorted(set(result.resistance))
    assert result.resistance.count(150.0) == 1


def test_insufficient_data_raises():
    df = _make_df([100] * 5, [95] * 5)
    with pytest.raises(ValueError):
        support_resistance_levels(df, order=5)
