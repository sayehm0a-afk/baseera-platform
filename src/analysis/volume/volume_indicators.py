"""Volume indicators: On-Balance Volume, Volume SMA, VWAP.

Pure computation over a pandas DataFrame -- no I/O, no database.
"""

import numpy as np
import pandas as pd

from src.analysis.indicators.trend import sma


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume. Starts at 0 (a common convention); each bar
    adds that bar's volume if close rose, subtracts it if close fell,
    and leaves OBV unchanged if close was flat.
    """
    close = df["close"]
    volume = df["volume"]
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Simple moving average of volume -- flags unusually high/low
    volume relative to its recent average.
    """
    return sma(df["volume"], period)


def vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Rolling Volume-Weighted Average Price over the trailing `period`
    bars: sum(typical_price * volume) / sum(volume), typical_price =
    (high + low + close) / 3.

    True VWAP is computed per intraday trading session from tick-level
    data and resets at the session open; this platform only has daily
    OHLCV bars, so this is the standard daily-bar analog -- a rolling
    N-bar volume-weighted average, not a session-anchored one. A bar
    range with zero total volume across the window is undefined (NaN).
    """
    if len(df) < period:
        raise ValueError(f"need at least {period} data points, got {len(df)}")

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    price_volume = typical_price * df["volume"]
    rolling_volume = df["volume"].rolling(window=period, min_periods=period).sum()
    rolling_price_volume = price_volume.rolling(window=period, min_periods=period).sum()

    with np.errstate(divide="ignore", invalid="ignore"):
        result = rolling_price_volume / rolling_volume
    return result.where(rolling_volume != 0)
