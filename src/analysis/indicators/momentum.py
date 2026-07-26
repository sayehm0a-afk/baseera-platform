"""Momentum indicators: RSI, MACD, Stochastic Oscillator.

Pure computation over pandas Series/DataFrame input -- no I/O, no
database.
"""

import numpy as np
import pandas as pd

from src.analysis.indicators.trend import ema, sma
from src.analysis.types import MACDResult, StochasticResult


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


def stochastic_oscillator(
    df: pd.DataFrame, k_period: int = 14, smooth_k: int = 3, d_period: int = 3
) -> StochasticResult:
    """The "full" Stochastic Oscillator: raw %K is the close's position
    within its `k_period`-bar high/low range (0-100), smoothed by
    `smooth_k` to produce the displayed %K line, and %D is that line's
    `d_period`-bar SMA (the signal line). Bounded [0, 100]; a bar whose
    `k_period`-bar range is exactly flat (high == low, no price
    movement at all) is defined as 50 (neutral), matching this module's
    existing convention for RSI's zero-loss case.
    """
    minimum = k_period + smooth_k + d_period - 2
    if len(df) < minimum:
        raise ValueError(f"need at least {minimum} data points, got {len(df)}")

    lowest_low = df["low"].rolling(window=k_period, min_periods=k_period).min()
    highest_high = df["high"].rolling(window=k_period, min_periods=k_period).max()
    price_range = highest_high - lowest_low

    with np.errstate(divide="ignore", invalid="ignore"):
        raw_k = 100 * (df["close"] - lowest_low) / price_range
    raw_k = raw_k.where(price_range != 0, 50.0)

    valid_raw_k = raw_k.dropna()
    percent_k = sma(valid_raw_k, smooth_k).reindex(df.index)
    valid_percent_k = percent_k.dropna()
    percent_d = sma(valid_percent_k, d_period).reindex(df.index)

    return StochasticResult(percent_k=percent_k, percent_d=percent_d)
