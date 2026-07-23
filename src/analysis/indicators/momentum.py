"""Momentum indicators: RSI, MACD.

Pure computation over pandas Series input -- no I/O, no database.
"""

import numpy as np
import pandas as pd

from src.analysis.indicators.trend import ema
from src.analysis.types import MACDResult


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index. Bounded [0, 100]. NaN for the
    first `period` bars (the diff plus the smoothing seed both consume
    warm-up bars).
    """
    if len(series) < period + 1:
        raise ValueError(f"need at least {period + 1} data points, got {len(series)}")

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    values_gain = gain.to_numpy(dtype="float64")
    values_loss = loss.to_numpy(dtype="float64")
    n = len(series)
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)

    avg_gain[period] = np.nanmean(values_gain[1 : period + 1])
    avg_loss[period] = np.nanmean(values_loss[1 : period + 1])
    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + values_gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + values_loss[i]) / period

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi_values = 100 - (100 / (1 + rs))
    # avg_loss == 0 means no losses in the window -> RSI is defined as 100
    rsi_values = np.where(avg_loss == 0, 100.0, rsi_values)
    rsi_values = np.where(np.isnan(avg_gain) | np.isnan(avg_loss), np.nan, rsi_values)

    return pd.Series(rsi_values, index=series.index)


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> MACDResult:
    """Moving Average Convergence Divergence: fast EMA minus slow EMA
    (the MACD line), an EMA of that line (the signal line), and their
    difference (the histogram).
    """
    if len(series) < slow + signal:
        raise ValueError(f"need at least {slow + signal} data points, got {len(series)}")

    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow

    valid_macd = macd_line.dropna()
    signal_on_valid = ema(valid_macd, signal)
    signal_line = signal_on_valid.reindex(series.index)

    histogram = macd_line - signal_line

    return MACDResult(macd_line=macd_line, signal_line=signal_line, histogram=histogram)
