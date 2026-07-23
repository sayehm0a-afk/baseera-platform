"""Volatility indicators: Bollinger Bands, ATR.

Pure computation over pandas Series/DataFrame input -- no I/O, no
database.
"""

import pandas as pd

from src.analysis.indicators._common import atr as atr
from src.analysis.indicators.trend import sma
from src.analysis.types import BollingerBandsResult

__all__ = ["atr", "bollinger_bands"]


def bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> BollingerBandsResult:
    """Bollinger Bands: an SMA middle band, with upper/lower bands at
    `num_std` population standard deviations (ddof=0, matching
    Bollinger's original definition) from the middle band.
    """
    if len(series) < period:
        raise ValueError(f"need at least {period} data points, got {len(series)}")

    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std

    return BollingerBandsResult(upper=upper, middle=middle, lower=lower)
