"""Unit tests for src.backtesting.regime -- pure function, synthetic
DataFrames, no database."""

import numpy as np
import pandas as pd

from src.backtesting.regime import classify_market_regime


def _df_from_closes(closes):
    n = len(closes)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    close = pd.Series(closes, index=index)
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": [1000.0] * n},
        index=index,
    )


def test_none_when_not_enough_history():
    df = _df_from_closes([100.0] * 10)
    assert classify_market_regime(df) is None


def test_uptrend_detected():
    df = _df_from_closes(list(np.linspace(100.0, 120.0, 25)))  # +20% over the window
    assert classify_market_regime(df) == "UPTREND"


def test_downtrend_detected():
    df = _df_from_closes(list(np.linspace(100.0, 80.0, 25)))  # -20%
    assert classify_market_regime(df) == "DOWNTREND"


def test_range_bound_detected():
    # Small oscillation around 100, net change well under the +/-5% threshold.
    closes = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(25)]
    assert classify_market_regime(df=_df_from_closes(closes)) == "RANGE_BOUND"


def test_high_volatility_takes_precedence_over_trend():
    rng = np.random.default_rng(7)
    # Large daily swings (~10% std) with a mild net uptrend.
    closes = [100.0]
    for _ in range(24):
        closes.append(closes[-1] * (1 + rng.normal(0.01, 0.10)))
    assert classify_market_regime(_df_from_closes(closes)) == "HIGH_VOLATILITY"
