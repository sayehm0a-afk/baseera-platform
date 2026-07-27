"""Support/resistance levels via swing-pivot (fractal) detection.

Pure computation over a pandas DataFrame -- no I/O, no database.
"""

import numpy as np
import pandas as pd

from src.analysis.types import SupportResistanceLevels


def support_resistance_levels(df: pd.DataFrame, order: int = 5) -> SupportResistanceLevels:
    """Classic swing-high/swing-low ("fractal") pivot detection: bar
    `i`'s high is a resistance pivot when it is the strict, unique
    maximum within the symmetric window `[i - order, i + order]`; a
    support pivot is the mirrored rule on the low. `order` bars are
    unavailable for pivot detection at each end of the series (a pivot
    needs `order` bars of confirmation on both sides), so the first and
    last `order` bars never produce a pivot.

    Returns sorted, deduplicated price levels -- not bar indices --
    since multiple pivots commonly repeat the same price.
    """
    minimum = order * 2 + 1
    if len(df) < minimum:
        raise ValueError(f"need at least {minimum} data points, got {len(df)}")

    highs = df["high"].to_numpy(dtype="float64")
    lows = df["low"].to_numpy(dtype="float64")
    n = len(df)

    resistance = set()
    support = set()
    for i in range(order, n - order):
        window_high = highs[i - order : i + order + 1]
        if highs[i] == window_high.max() and np.sum(window_high == highs[i]) == 1:
            resistance.add(float(highs[i]))

        window_low = lows[i - order : i + order + 1]
        if lows[i] == window_low.min() and np.sum(window_low == lows[i]) == 1:
            support.add(float(lows[i]))

    return SupportResistanceLevels(support=sorted(support), resistance=sorted(resistance))
