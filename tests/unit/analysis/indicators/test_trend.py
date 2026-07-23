"""Unit tests for src.analysis.indicators.trend: SMA, EMA, ADX, SuperTrend.

Reference values below are hand-computed by executing each indicator's
documented algorithm by hand on a small, fully worked series (not copied
from the implementation's source), plus independent, freshly-written
non-vectorized loop implementations for cross-checking the vectorized
production code against longer, randomly generated series -- the
technique the approved M2.2 spec calls for on recursive/stateful
indicators, where an off-by-one or window-edge bug is the most likely
defect class.
"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators.trend import adx, ema, sma, supertrend


def _make_ohlcv(n, seed):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0, 1, n))
    low = close - np.abs(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(1000, 10000, n).astype(float)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------


def test_sma_reference_values():
    # mean(22,24,23)=23, mean(24,23,25)=24, mean(23,25,26)=74/3, ...
    series = pd.Series([22, 24, 23, 25, 26, 25, 27, 28, 27, 29], dtype="float64")
    result = sma(series, 3)
    expected = [
        np.nan, np.nan, 23.0, 24.0, 74 / 3, 76 / 3, 26.0, 80 / 3, 82 / 3, 28.0,
    ]
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


def test_sma_nan_warmup_length():
    series = pd.Series(range(10), dtype="float64")
    result = sma(series, 4)
    assert result.iloc[:3].isna().all()
    assert result.iloc[3:].notna().all()


def test_sma_invalid_period_raises():
    with pytest.raises(ValueError):
        sma(pd.Series([1.0, 2.0, 3.0]), 0)


def test_sma_insufficient_data_raises():
    with pytest.raises(ValueError):
        sma(pd.Series([1.0, 2.0]), 5)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


def test_ema_reference_values():
    # period=3, alpha=0.5, SMA-seeded at index 2.
    series = pd.Series([22, 24, 23, 25, 26, 25, 27, 28, 27, 29], dtype="float64")
    result = ema(series, 3)
    expected = [
        np.nan, np.nan, 23.0, 24.0, 25.0, 25.0, 26.0, 27.0, 27.0, 28.0,
    ]
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


def _reference_ema(values, period):
    """Independent, freshly-written loop implementation (SMA-seeded)."""
    alpha = 2.0 / (period + 1)
    result = [float("nan")] * len(values)
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * alpha + result[i - 1]
    return result


def test_ema_matches_independent_reference_loop():
    df = _make_ohlcv(40, seed=1)
    values = df["close"].tolist()
    expected = _reference_ema(values, 7)
    result = ema(df["close"], 7)
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


def test_ema_invalid_period_raises():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0, 3.0]), 0)


def test_ema_insufficient_data_raises():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0]), 5)


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------


def _reference_adx(df, period):
    """Independent, freshly-written loop implementation of Wilder's ADX."""
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()
    n = len(highs)

    trs = [float("nan")] * n
    plus_dms = [float("nan")] * n
    minus_dms = [float("nan")] * n
    trs[0] = highs[0] - lows[0]
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dms[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dms[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        trs[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    def wilder(values):
        result = [float("nan")] * len(values)
        if len(values) <= period:
            return result
        window = [v for v in values[1 : period + 1] if v == v]  # skip NaN, like np.nanmean
        result[period] = sum(window) / len(window) if window else float("nan")
        for i in range(period + 1, len(values)):
            result[i] = (result[i - 1] * (period - 1) + values[i]) / period
        return result

    atr_ref = wilder(trs)
    plus_dm_smooth = wilder(plus_dms)
    minus_dm_smooth = wilder(minus_dms)

    dx = [float("nan")] * n
    for i in range(n):
        a = atr_ref[i]
        if a != a or a == 0:
            continue
        plus_di = 100 * plus_dm_smooth[i] / a
        minus_di = 100 * minus_dm_smooth[i] / a
        di_sum = plus_di + minus_di
        dx[i] = 100 * abs(plus_di - minus_di) / di_sum if di_sum != 0 else 0.0

    return wilder(dx)


def test_adx_matches_independent_reference_loop():
    df = _make_ohlcv(50, seed=2)
    expected = _reference_adx(df, 14)
    result = adx(df, 14)
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-6, atol=1e-9, equal_nan=True)


def test_adx_bounded_zero_to_hundred():
    df = _make_ohlcv(60, seed=3)
    result = adx(df, 14).dropna()
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_adx_insufficient_data_raises():
    df = _make_ohlcv(20, seed=4)
    with pytest.raises(ValueError):
        adx(df, 14)


# ---------------------------------------------------------------------------
# SuperTrend
# ---------------------------------------------------------------------------


def test_supertrend_direction_is_always_plus_or_minus_one():
    df = _make_ohlcv(60, seed=5)
    result = supertrend(df, 10, 3.0)
    non_nan = result.direction.dropna()
    assert not non_nan.empty
    assert set(non_nan.unique().tolist()) <= {1.0, -1.0}


def test_supertrend_strong_uptrend_is_bullish_throughout():
    n = 40
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.arange(n) * 2.0  # steadily, sharply rising
    df = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.full(n, 1000.0),
        },
        index=index,
    )
    result = supertrend(df, 10, 3.0)
    non_nan = result.direction.dropna()
    assert (non_nan == 1.0).all()


def test_supertrend_strong_downtrend_settles_bearish():
    # The very first computed bar's direction is initialized to +1 by
    # convention (see supertrend()'s `direction[start] = 1`) regardless
    # of subsequent price action, so a sharp downtrend needs a few bars
    # to flip -- the meaningful invariant is that it settles into -1 and
    # stays there, not that every single bar (including the seed) is -1.
    n = 40
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 300 - np.arange(n) * 2.0  # steadily, sharply falling
    df = pd.DataFrame(
        {
            "open": close + 0.2,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.full(n, 1000.0),
        },
        index=index,
    )
    result = supertrend(df, 10, 3.0)
    non_nan = result.direction.dropna()
    assert (non_nan.iloc[-10:] == -1.0).all()


def test_supertrend_insufficient_data_raises():
    df = _make_ohlcv(10, seed=6)
    with pytest.raises(ValueError):
        supertrend(df, 10, 3.0)
