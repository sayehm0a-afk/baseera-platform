"""Small pandas.Series helpers shared by the AI Decision Intelligence
Layer's contributors (momentum/volume/risk) -- reading a series'
latest non-null value, or the value N non-null observations back, is
needed by more than one of them, so it lives once here rather than
being copy-pasted into each contributor module."""

from typing import Optional

import pandas as pd


def latest_value(series: pd.Series) -> Optional[float]:
    non_null = series.dropna()
    if non_null.empty:
        return None
    return non_null.iloc[-1]


def nth_back_value(series: pd.Series, n: int) -> Optional[float]:
    """The value `n` non-null observations before the latest one, or
    `None` if there isn't enough history."""
    non_null = series.dropna()
    if len(non_null) <= n:
        return None
    return non_null.iloc[-1 - n]
