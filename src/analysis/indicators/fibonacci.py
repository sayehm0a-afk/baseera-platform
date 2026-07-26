"""Fibonacci retracement levels.

Pure computation over a pandas DataFrame -- no I/O, no database.
Unlike the other indicators in this package, the result isn't a
per-bar series: it's one set of static price levels derived from a
single swing high and swing low found within the analyzed window.
"""

from typing import Optional

import pandas as pd

from src.analysis.types import FibonacciLevels

_RETRACEMENT_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def fibonacci_retracement_levels(
    df: pd.DataFrame, lookback: Optional[int] = None
) -> FibonacciLevels:
    """Finds the highest high and lowest low within the last `lookback`
    bars (the full DataFrame if `lookback` is None) and derives the
    standard retracement levels (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%,
    100%) between them.

    Direction matters: if the swing low occurred at or before the swing
    high (an up move), levels are measured downward from the high --
    the conventional "retracement of an uptrend" reading. If the high
    came first (a down move), levels are measured upward from the low.
    """
    window = df if lookback is None else df.iloc[-lookback:]
    if len(window) < 2:
        raise ValueError(f"need at least 2 data points, got {len(window)}")

    swing_high = float(window["high"].max())
    swing_high_at = window["high"].idxmax()
    swing_low = float(window["low"].min())
    swing_low_at = window["low"].idxmin()

    is_uptrend = swing_low_at <= swing_high_at
    price_range = swing_high - swing_low

    if is_uptrend:
        levels = {f"{ratio * 100:.1f}": swing_high - price_range * ratio for ratio in _RETRACEMENT_RATIOS}
    else:
        levels = {f"{ratio * 100:.1f}": swing_low + price_range * ratio for ratio in _RETRACEMENT_RATIOS}

    return FibonacciLevels(
        swing_high=swing_high,
        swing_high_at=swing_high_at,
        swing_low=swing_low,
        swing_low_at=swing_low_at,
        is_uptrend=is_uptrend,
        levels=levels,
    )
