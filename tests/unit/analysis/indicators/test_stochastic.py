"""Unit tests for src.analysis.indicators.momentum.stochastic_oscillator.

Reference values are hand-computed by executing the documented "full
stochastic" algorithm by hand on a small series.
"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators.momentum import stochastic_oscillator


def _make_df(closes):
    # Deliberately widen high/low around close so the k_period window's
    # high/low range is unambiguous and easy to hand-verify.
    closes = pd.Series(closes, dtype="float64")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": np.full(len(closes), 1000.0),
        }
    )


def test_stochastic_bounded_zero_to_hundred():
    df = _make_df(np.random.default_rng(21).normal(100, 5, 40))
    result = stochastic_oscillator(df, k_period=14, smooth_k=3, d_period=3)
    for series in (result.percent_k, result.percent_d):
        valid = series.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


def test_stochastic_flat_range_is_neutral_fifty():
    # Every bar identical -> the k_period window's high == low everywhere,
    # so raw %K is undefined and must fall back to the documented 50.0.
    df = _make_df(np.full(30, 100.0))
    result = stochastic_oscillator(df, k_period=14, smooth_k=3, d_period=3)
    assert (result.percent_k.dropna() == 50.0).all()
    assert (result.percent_d.dropna() == 50.0).all()


def test_stochastic_at_the_top_of_its_range_reads_near_100():
    # A strictly rising series: each bar's close is the highest close
    # (and thus at/near the top of the rolling high/low range) seen so far.
    df = _make_df(np.arange(30, dtype="float64"))
    result = stochastic_oscillator(df, k_period=14, smooth_k=1, d_period=1)
    assert result.percent_k.dropna().iloc[-1] > 95.0


def test_stochastic_at_the_bottom_of_its_range_reads_near_zero():
    df = _make_df(np.arange(30, 0, -1, dtype="float64"))
    result = stochastic_oscillator(df, k_period=14, smooth_k=1, d_period=1)
    assert result.percent_k.dropna().iloc[-1] < 5.0


def test_stochastic_percent_d_is_a_moving_average_of_percent_k():
    df = _make_df(np.random.default_rng(22).normal(100, 5, 40))
    result = stochastic_oscillator(df, k_period=14, smooth_k=3, d_period=3)
    expected_d = result.percent_k.rolling(window=3, min_periods=3).mean()
    np.testing.assert_allclose(
        result.percent_d.dropna().to_numpy(),
        expected_d.dropna().to_numpy(),
        rtol=1e-9,
    )


def test_stochastic_insufficient_data_raises():
    df = _make_df(np.arange(10, dtype="float64"))
    with pytest.raises(ValueError):
        stochastic_oscillator(df, k_period=14, smooth_k=3, d_period=3)
