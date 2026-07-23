"""Volume indicators: On-Balance Volume, Volume SMA.

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
