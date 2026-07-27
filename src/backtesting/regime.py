"""Per-symbol market-regime classification.

There is no broad-market regime signal available in this codebase --
`MarketSnapshot` (the TASI-index model) exists but is never populated
by any ingestion job (confirmed during this milestone's architecture
audit). Rather than fabricate index history, "market regime" here is
classified per symbol, from that symbol's own recent price action --
a real, honestly-labeled, if narrower, signal. Uses only bars up to
and including the evaluation date (the same DataFrame
data_access.load_as_of_dataset already builds from), so this carries
no look-ahead risk of its own.
"""

from typing import Optional

import pandas as pd

_LOOKBACK_BARS = 20
_TREND_THRESHOLD = 0.05  # +/-5% over the lookback window counts as trending
_HIGH_VOLATILITY_ANNUALIZED_STD = 0.35  # ~35% annualized daily-return volatility


def classify_market_regime(df: pd.DataFrame) -> Optional[str]:
    """One of "UPTREND", "DOWNTREND", "RANGE_BOUND", "HIGH_VOLATILITY",
    or `None` if there isn't enough history (< _LOOKBACK_BARS bars) to
    classify. High volatility is checked first and takes precedence
    over trend direction -- a sharply trending-but-choppy market is
    still a high-volatility regime for risk purposes.
    """
    if len(df) < _LOOKBACK_BARS:
        return None

    window = df["close"].iloc[-_LOOKBACK_BARS:]
    daily_returns = window.pct_change().dropna()
    if daily_returns.empty:
        return None

    annualized_std = daily_returns.std() * (252 ** 0.5)
    if annualized_std >= _HIGH_VOLATILITY_ANNUALIZED_STD:
        return "HIGH_VOLATILITY"

    total_change = (window.iloc[-1] - window.iloc[0]) / window.iloc[0] if window.iloc[0] != 0 else 0.0
    if total_change >= _TREND_THRESHOLD:
        return "UPTREND"
    if total_change <= -_TREND_THRESHOLD:
        return "DOWNTREND"
    return "RANGE_BOUND"
