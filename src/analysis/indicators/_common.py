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


def wilder_smooth(series: pd.Series, period: int, seed_start: int = 1) -> pd.Series:
    """Wilder's smoothing: seed with the simple mean of
    values[seed_start:seed_start+period], then recursively
    smoothed[i] = (smoothed[i-1] * (period - 1) + value[i]) / period.

    `seed_start` is the index of the first value eligible for the seed
    average -- defaults to 1, Wilder's original convention for a
    diff-derived series (true range, +DM/-DM) whose only undefined
    value is index 0. A series that is itself only valid starting
    later (e.g. DX, undefined until index `period` because it depends
    on two already-smoothed series) must pass `seed_start=period` so
    the seed genuinely averages `period` real values -- otherwise
    `np.nanmean` silently ignores the leading NaNs and seeds from a
    single value, producing a materially wrong result for roughly the
    next `period` bars (2026-09-16 audit finding, ADX).
    """
    values = series.to_numpy(dtype="float64")
    result = np.full(len(values), np.nan)
    seed_index = seed_start + period - 1
    if seed_index >= len(values):
        return pd.Series(result, index=series.index)
    result[seed_index] = np.nanmean(values[seed_start : seed_start + period])
    for i in range(seed_index + 1, len(values)):
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
