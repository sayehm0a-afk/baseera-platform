"""Internal helpers shared by trend.py and volatility.py.

Not part of the public indicator API (leading underscore on the
module itself signals that) -- exists purely to avoid a circular
import between trend.py (needs ATR-style smoothing for ADX/SuperTrend)
and volatility.py (needs `sma` from trend.py for Bollinger Bands, and
is ATR's documented public home per the M2.2 folder structure).
"""

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    )
    return ranges.max(axis=1)


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: seed with the simple mean of values[1:period+1],
    then recursively smoothed[i] = (smoothed[i-1] * (period - 1) + value[i]) / period.
    """
    values = series.to_numpy(dtype="float64")
    result = np.full(len(values), np.nan)
    if len(values) <= period:
        return pd.Series(result, index=series.index)
    result[period] = np.nanmean(values[1 : period + 1])
    for i in range(period + 1, len(values)):
        result[i] = (result[i - 1] * (period - 1) + values[i]) / period
    return pd.Series(result, index=series.index)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range -- the actual implementation.
    Re-exported from src.analysis.indicators.volatility, its documented
    public location; also used internally by trend.py's ADX/SuperTrend.
    """
    if len(df) < period + 1:
        raise ValueError(f"need at least {period + 1} data points, got {len(df)}")
    return wilder_smooth(true_range(df), period)
