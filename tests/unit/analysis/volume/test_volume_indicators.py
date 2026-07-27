"""Unit tests for src.analysis.volume.volume_indicators: OBV, Volume SMA,
VWAP.

Reference values are hand-computed by executing the documented
algorithm by hand on a small series.
"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.volume.volume_indicators import obv, volume_sma, vwap


def _make_df():
    return pd.DataFrame(
        {
            "open": [10, 11, 10, 12, 12, 11],
            "high": [10.5, 11.5, 10.5, 12.5, 12.5, 11.5],
            "low": [9.5, 10.5, 9.5, 11.5, 11.5, 10.5],
            "close": [10, 11, 10, 12, 12, 11],
            "volume": [100.0, 150.0, 200.0, 50.0, 80.0, 90.0],
        }
    )


def test_obv_reference_values():
    df = _make_df()
    result = obv(df)
    expected = [0.0, 150.0, -50.0, 0.0, 0.0, -90.0]
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9)


def test_obv_starts_at_zero():
    df = _make_df()
    assert obv(df).iloc[0] == 0.0


def test_obv_monotonic_up_only_increases():
    n = 10
    df = pd.DataFrame(
        {
            "open": np.arange(n, dtype="float64"),
            "high": np.arange(n, dtype="float64") + 0.5,
            "low": np.arange(n, dtype="float64") - 0.5,
            "close": np.arange(n, dtype="float64"),
            "volume": np.full(n, 100.0),
        }
    )
    result = obv(df)
    assert (result.diff().dropna() >= 0).all()


def test_volume_sma_reference_values():
    df = _make_df()
    result = volume_sma(df, period=3)
    expected = [np.nan, np.nan, 150.0, 400 / 3, 110.0, 220 / 3]
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-9, equal_nan=True)


def test_volume_sma_insufficient_data_raises():
    df = _make_df().iloc[:2]
    with pytest.raises(ValueError):
        volume_sma(df, period=5)


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------


def test_vwap_reference_value_over_full_window():
    df = _make_df()
    result = vwap(df, period=6)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    expected_last = (typical_price * df["volume"]).sum() / df["volume"].sum()
    assert result.dropna().iloc[-1] == pytest.approx(expected_last)


def test_vwap_matches_a_simple_average_when_volume_is_constant():
    # Equal volume on every bar reduces VWAP to a plain average of the
    # typical price over the window -- an easy independent check.
    n = 10
    df = pd.DataFrame(
        {
            "open": np.arange(n, dtype="float64") + 100,
            "high": np.arange(n, dtype="float64") + 100.5,
            "low": np.arange(n, dtype="float64") + 99.5,
            "close": np.arange(n, dtype="float64") + 100,
            "volume": np.full(n, 500.0),
        }
    )
    result = vwap(df, period=5)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    expected = typical_price.rolling(window=5, min_periods=5).mean()
    np.testing.assert_allclose(
        result.dropna().to_numpy(), expected.dropna().to_numpy(), rtol=1e-9
    )


def test_vwap_is_nan_for_the_warmup_period():
    df = _make_df()
    result = vwap(df, period=6)
    assert result.iloc[:5].isna().all()


def test_vwap_insufficient_data_raises():
    df = _make_df().iloc[:2]
    with pytest.raises(ValueError):
        vwap(df, period=6)
