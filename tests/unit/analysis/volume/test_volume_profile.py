"""Unit tests for src.analysis.volume.volume_profile."""

import pandas as pd
import pytest

from src.analysis.volume.volume_profile import volume_profile


def _make_df(closes, volumes):
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": volumes,
        }
    )


def test_bin_volumes_sum_to_total_volume():
    df = _make_df(
        closes=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        volumes=[100, 100, 100, 100, 500, 100, 100, 100, 100, 100, 100],
    )
    result = volume_profile(df, num_bins=5)
    assert sum(result.bin_volumes) == pytest.approx(df["volume"].sum())


def test_point_of_control_is_the_highest_volume_bucket():
    df = _make_df(
        closes=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        volumes=[100, 100, 100, 100, 500, 100, 100, 100, 100, 100, 100],
    )
    result = volume_profile(df, num_bins=5)
    # Bar at close=14 (the 500-volume bar) sits in the middle price bucket.
    assert 13.0 <= result.point_of_control <= 17.0


def test_bin_edges_span_the_full_high_low_range():
    df = _make_df(closes=[10, 20, 30], volumes=[100, 100, 100])
    result = volume_profile(df, num_bins=3)
    assert result.bin_edges[0] == pytest.approx(df["low"].min())
    assert result.bin_edges[-1] == pytest.approx(df["high"].max())
    assert len(result.bin_edges) == 4
    assert len(result.bin_volumes) == 3


def test_rejects_zero_bins():
    df = _make_df(closes=[10, 20], volumes=[100, 100])
    with pytest.raises(ValueError):
        volume_profile(df, num_bins=0)


def test_rejects_empty_dataframe():
    df = _make_df(closes=[], volumes=[])
    with pytest.raises(ValueError):
        volume_profile(df, num_bins=5)


def test_rejects_zero_price_range():
    # high == low on every bar, and identical across bars -- the whole
    # DataFrame's high/low range collapses to a single price.
    df = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0],
            "high": [10.0, 10.0, 10.0],
            "low": [10.0, 10.0, 10.0],
            "close": [10.0, 10.0, 10.0],
            "volume": [100.0, 100.0, 100.0],
        }
    )
    with pytest.raises(ValueError):
        volume_profile(df, num_bins=5)
