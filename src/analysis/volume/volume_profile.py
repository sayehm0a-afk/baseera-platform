"""Volume profile: an approximate volume-at-price histogram.

Pure computation over a pandas DataFrame -- no I/O, no database.
"""

import numpy as np
import pandas as pd

from src.analysis.types import VolumeProfileResult


def volume_profile(df: pd.DataFrame, num_bins: int = 10) -> VolumeProfileResult:
    """Buckets the DataFrame's full high/low price range into `num_bins`
    equal-width bins and sums each bar's entire volume into the bin
    containing that bar's typical price ((high+low+close)/3).

    This is a daily-bar approximation, not a true intrabar
    volume-at-price profile: real volume profiles distribute a single
    bar's volume across the prices it actually traded at within that
    bar, which requires tick-level data this platform does not have.
    Documented here rather than silently treated as more precise than
    it is.

    `point_of_control` is the midpoint price of the highest-volume bin
    -- the level with the most (approximated) trading activity.
    """
    if num_bins < 1:
        raise ValueError("num_bins must be >= 1")
    if df.empty:
        raise ValueError("cannot build a volume profile over an empty DataFrame")

    low = float(df["low"].min())
    high = float(df["high"].max())
    if high == low:
        raise ValueError("cannot build a volume profile over a zero price range")

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    edges = np.linspace(low, high, num_bins + 1)
    bin_labels = pd.cut(typical_price, bins=edges, include_lowest=True)
    bin_volumes_series = df["volume"].groupby(bin_labels, observed=False).sum()
    bin_volumes_series = bin_volumes_series.reindex(bin_labels.cat.categories, fill_value=0.0)
    bin_volumes = [float(v) for v in bin_volumes_series.to_numpy(dtype="float64")]

    poc_index = int(np.argmax(bin_volumes))
    point_of_control = float((edges[poc_index] + edges[poc_index + 1]) / 2)

    return VolumeProfileResult(
        bin_edges=[float(e) for e in edges],
        bin_volumes=bin_volumes,
        point_of_control=point_of_control,
    )
