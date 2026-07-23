"""Unit tests for src.analysis.indicators.volatility: Bollinger Bands, ATR.

Reference values are hand-computed by executing the documented algorithm
by hand on a small, fully worked OHLC(V) series.
"""

import math

import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators.volatility import atr, bollinger_bands


def test_bollinger_bands_reference_values():
    series = pd.Series([10, 12, 11, 13, 15], dtype="float64")
    result = bollinger_bands(series, period=3, num_std=2.0)

    expected_middle = [np.nan, np.nan, 11.0, 12.0, 13.0]
    # population std (ddof=0) of each rolling window of 3
    std_2 = math.sqrt(2 / 3)
    std_4 = math.sqrt(8 / 3)
    expected_upper = [np.nan, np.nan, 11.0 + 2 * std_2, 12.0 + 2 * std_2, 13.0 + 2 * std_4]
    expected_lower = [np.nan, np.nan, 11.0 - 2 * std_2, 12.0 - 2 * std_2, 13.0 - 2 * std_4]

    np.testing.assert_allclose(result.middle.to_numpy(), expected_middle, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(result.upper.to_numpy(), expected_upper, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(result.lower.to_numpy(), expected_lower, rtol=1e-9, equal_nan=True)


def test_bollinger_bands_middle_matches_sma():
    series = pd.Series(np.linspace(50, 80, 30))
    result = bollinger_bands(series, period=5, num_std=2.0)
    from src.analysis.indicators.trend import sma

    np.testing.assert_allclose(
        result.middle.to_numpy(), sma(series, 5).to_numpy(), rtol=1e-12, equal_nan=True
    )


def test_bollinger_bands_upper_never_below_lower():
    series = pd.Series(np.random.default_rng(7).normal(100, 5, 40))
    result = bollinger_bands(series, period=10, num_std=2.0)
    non_nan = result.upper.notna()
    assert (result.upper[non_nan] >= result.lower[non_nan]).all()


def test_bollinger_bands_insufficient_data_raises():
    with pytest.raises(ValueError):
        bollinger_bands(pd.Series([1.0, 2.0]), period=5)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------


def test_atr_reference_values():
    df = pd.DataFrame(
        {
            "open": [8.5, 9.5, 10.0, 11.0, 10.5],
            "high": [10, 11, 10.5, 12, 11],
            "low": [8, 9, 9.5, 10, 10],
            "close": [9, 10, 10, 11.5, 10.5],
            "volume": [100.0] * 5,
        }
    )
    result = atr(df, period=3)
    expected = [np.nan, np.nan, np.nan, 5 / 3, 29 / 18]
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


def test_atr_is_non_negative():
    df = pd.DataFrame(
        {
            "open": np.random.default_rng(8).normal(100, 2, 30),
            "high": np.random.default_rng(9).normal(102, 2, 30),
            "low": np.random.default_rng(10).normal(98, 2, 30),
            "close": np.random.default_rng(11).normal(100, 2, 30),
            "volume": np.full(30, 1000.0),
        }
    )
    # ensure high >= low for a valid OHLC frame
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1) + 0.5
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1) - 0.5
    result = atr(df, period=14).dropna()
    assert (result >= 0).all()


def test_atr_insufficient_data_raises():
    df = pd.DataFrame(
        {"open": [1.0, 2.0], "high": [1.5, 2.5], "low": [0.5, 1.5], "close": [1.2, 2.2], "volume": [10.0, 10.0]}
    )
    with pytest.raises(ValueError):
        atr(df, period=14)
