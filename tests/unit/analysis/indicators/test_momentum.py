"""Unit tests for src.analysis.indicators.momentum: RSI, MACD.

RSI reference values are hand-computed by executing Wilder's algorithm
by hand on a small series (rs[3]=4 exactly, rs[5]=76/25 exactly, so the
expected RSI values reduce to exact fractions). MACD is cross-checked
against a freshly-written, independent (non-vectorized) EMA loop, since
it is the most deeply recursive/composite indicator in this milestone.
"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators.momentum import macd, rsi


def test_rsi_reference_values():
    series = pd.Series([44, 44.5, 44.25, 44.75, 44.5, 44.9], dtype="float64")
    result = rsi(series, period=3)

    expected = [
        np.nan,
        np.nan,
        np.nan,
        80.0,  # rs=4 -> 100 - 100/5
        800 / 13,  # rs=1.6 -> 100 - 100/2.6
        7600 / 101,  # rs=76/25=3.04 -> 100 - 100/4.04
    ]
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


def test_rsi_all_gains_is_100():
    series = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19], dtype="float64")
    result = rsi(series, period=3)
    assert (result.dropna() == 100.0).all()


def test_rsi_bounded_zero_to_hundred():
    series = pd.Series(np.random.default_rng(12).normal(100, 3, 40))
    result = rsi(series, period=14).dropna()
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_rsi_insufficient_data_raises():
    with pytest.raises(ValueError):
        rsi(pd.Series([1.0, 2.0]), period=14)


def _reference_rsi(values, period):
    """Independent, freshly-written loop implementation of Wilder's RSI."""
    n = len(values)
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        delta = values[i] - values[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)

    avg_gain = [float("nan")] * n
    avg_loss = [float("nan")] * n
    avg_gain[period] = sum(gains[1 : period + 1]) / period
    avg_loss[period] = sum(losses[1 : period + 1]) / period
    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

    result = [float("nan")] * n
    for i in range(period, n):
        if avg_loss[i] == 0:
            result[i] = 100.0
        else:
            rs = avg_gain[i] / avg_loss[i]
            result[i] = 100 - 100 / (1 + rs)
    return result


def test_rsi_matches_independent_reference_loop():
    series = pd.Series(np.random.default_rng(13).normal(50, 5, 45))
    expected = _reference_rsi(series.tolist(), 14)
    result = rsi(series, period=14)
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------


def _reference_ema_loop(values, period):
    alpha = 2.0 / (period + 1)
    result = [float("nan")] * len(values)
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * alpha + result[i - 1]
    return result


def test_macd_matches_independent_reference_loop():
    series = pd.Series(np.random.default_rng(14).normal(100, 4, 60))
    values = series.tolist()

    fast_ref = _reference_ema_loop(values, 12)
    slow_ref = _reference_ema_loop(values, 26)
    macd_line_ref = [
        f - s if (f == f and s == s) else float("nan") for f, s in zip(fast_ref, slow_ref)
    ]
    valid = [v for v in macd_line_ref if v == v]
    signal_ref_on_valid = _reference_ema_loop(valid, 9)
    signal_ref = [float("nan")] * len(values)
    idx = 0
    for i, v in enumerate(macd_line_ref):
        if v == v:
            signal_ref[i] = signal_ref_on_valid[idx]
            idx += 1

    result = macd(series, fast=12, slow=26, signal=9)

    np.testing.assert_allclose(result.macd_line.to_numpy(), macd_line_ref, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(result.signal_line.to_numpy(), signal_ref, rtol=1e-9, equal_nan=True)


def test_macd_histogram_is_macd_minus_signal():
    series = pd.Series(np.random.default_rng(15).normal(100, 4, 60))
    result = macd(series)
    expected_histogram = result.macd_line - result.signal_line
    np.testing.assert_allclose(
        result.histogram.to_numpy(), expected_histogram.to_numpy(), rtol=1e-12, equal_nan=True
    )


def test_macd_insufficient_data_raises():
    with pytest.raises(ValueError):
        macd(pd.Series(np.zeros(20)), fast=12, slow=26, signal=9)
