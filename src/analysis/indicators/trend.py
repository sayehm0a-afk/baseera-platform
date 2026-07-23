"""Trend indicators: SMA, EMA, ADX, SuperTrend.

Every function here is a pure computation over pandas Series/DataFrame
input -- no I/O, no database, no awareness of the indicator registry
that references these functions from src/analysis/registry.py.
"""

import numpy as np
import pandas as pd

from src.analysis.indicators._common import atr, wilder_smooth
from src.analysis.types import SuperTrendResult


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average. NaN for the first `period - 1` bars."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(series) < period:
        raise ValueError(f"need at least {period} data points, got {len(series)}")
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average, seeded with the SMA of the first
    `period` values (the standard charting-platform convention) rather
    than pandas' `.ewm(adjust=False)` default of seeding with the first
    raw data point -- the two conventions converge after enough bars,
    but disagree on the first several, and this matches published
    reference values.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(series) < period:
        raise ValueError(f"need at least {period} data points, got {len(series)}")

    alpha = 2.0 / (period + 1)
    values = series.to_numpy(dtype="float64")
    result = np.full(len(values), np.nan)
    result[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * alpha + result[i - 1]
    return pd.Series(result, index=series.index)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average Directional Index. Bounded [0, 100]; NaN until
    enough bars have accumulated for the double-smoothing (+DM/-DM
    smoothing, then DX smoothing) to produce a value.
    """
    if len(df) < period * 2:
        raise ValueError(f"need at least {period * 2} data points, got {len(df)}")

    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index
    )

    atr_values = atr(df, period)
    plus_dm_smooth = wilder_smooth(plus_dm, period)
    minus_dm_smooth = wilder_smooth(minus_dm, period)

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100 * (plus_dm_smooth / atr_values)
        minus_di = 100 * (minus_dm_smooth / atr_values)
        di_sum = plus_di + minus_di
        dx = 100 * (plus_di - minus_di).abs() / di_sum
    dx = dx.where(di_sum != 0, 0.0)

    return wilder_smooth(dx, period)


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> SuperTrendResult:
    """SuperTrend: an ATR-band trend-following indicator. `direction`
    is +1 (bullish, price above the trend line) or -1 (bearish) at
    every bar from the first fully-computed one onward.
    """
    if len(df) < period + 2:
        raise ValueError(f"need at least {period + 2} data points, got {len(df)}")

    atr_values = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    basic_upper = (hl2 + multiplier * atr_values).to_numpy(dtype="float64")
    basic_lower = (hl2 - multiplier * atr_values).to_numpy(dtype="float64")
    close = df["close"].to_numpy(dtype="float64")

    n = len(df)
    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    trend = np.full(n, np.nan)
    direction = np.full(n, np.nan)

    start = int(np.argmax(~np.isnan(basic_upper)))
    final_upper[start] = basic_upper[start]
    final_lower[start] = basic_lower[start]
    trend[start] = final_lower[start]
    direction[start] = 1

    for i in range(start + 1, n):
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        if trend[i - 1] == final_upper[i - 1] and close[i] <= final_upper[i]:
            trend[i], direction[i] = final_upper[i], -1
        elif trend[i - 1] == final_upper[i - 1] and close[i] > final_upper[i]:
            trend[i], direction[i] = final_lower[i], 1
        elif trend[i - 1] == final_lower[i - 1] and close[i] >= final_lower[i]:
            trend[i], direction[i] = final_lower[i], 1
        else:
            trend[i], direction[i] = final_upper[i], -1

    return SuperTrendResult(
        trend=pd.Series(trend, index=df.index),
        direction=pd.Series(direction, index=df.index),
    )
