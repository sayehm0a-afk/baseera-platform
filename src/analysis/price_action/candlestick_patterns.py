"""Candlestick pattern detection.

Five well-defined, unambiguous single/two-bar patterns -- deliberately
not an exhaustive pattern library. Each is a pure geometric check on
the bar(s) in question; none consider surrounding trend context (e.g.
"Hammer after a downtrend" vs. just "Hammer-shaped bar"), which is a
documented simplification, not an oversight -- trend-context-aware
pattern confirmation is a natural extension point for a future
Composite Indicator Engine or Signal Engine layered on top of this
module's output, not this module's job.

Pure computation over a pandas DataFrame -- no I/O, no database.
"""

from typing import List

import pandas as pd

from src.analysis.types import PatternMatch

_DOJI_BODY_RATIO = 0.1
_LONG_WICK_RATIO = 2.0


def _body(open_: float, close: float) -> float:
    return abs(close - open_)


def _range(high: float, low: float) -> float:
    return high - low


def _is_doji(open_: float, high: float, low: float, close: float) -> bool:
    bar_range = _range(high, low)
    if bar_range == 0:
        return False
    return _body(open_, close) <= _DOJI_BODY_RATIO * bar_range


def _is_hammer(open_: float, high: float, low: float, close: float) -> bool:
    body = _body(open_, close)
    if body == 0:
        return False
    lower_wick = min(open_, close) - low
    upper_wick = high - max(open_, close)
    return lower_wick >= _LONG_WICK_RATIO * body and upper_wick <= body


def _is_shooting_star(open_: float, high: float, low: float, close: float) -> bool:
    body = _body(open_, close)
    if body == 0:
        return False
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return upper_wick >= _LONG_WICK_RATIO * body and lower_wick <= body


def _is_bullish_engulfing(
    prev_open: float, prev_close: float, open_: float, close: float
) -> bool:
    prev_bearish = prev_close < prev_open
    curr_bullish = close > open_
    engulfs = open_ < prev_close and close > prev_open
    return prev_bearish and curr_bullish and engulfs


def _is_bearish_engulfing(
    prev_open: float, prev_close: float, open_: float, close: float
) -> bool:
    prev_bullish = prev_close > prev_open
    curr_bearish = close < open_
    engulfs = open_ > prev_close and close < prev_open
    return prev_bullish and curr_bearish and engulfs


def detect_patterns(df: pd.DataFrame) -> List[PatternMatch]:
    """Scan every bar (and, for the two-bar patterns, every consecutive
    pair) and return one PatternMatch per detected occurrence. A single
    bar may match more than one pattern (e.g. a Doji can simultaneously
    resemble a very small Hammer) -- both are reported.
    """
    matches: List[PatternMatch] = []

    for timestamp, row in df.iterrows():
        open_, high, low, close = row["open"], row["high"], row["low"], row["close"]

        if _is_doji(open_, high, low, close):
            matches.append(PatternMatch("doji", timestamp, bullish=close >= open_))
        if _is_hammer(open_, high, low, close):
            matches.append(PatternMatch("hammer", timestamp, bullish=True))
        if _is_shooting_star(open_, high, low, close):
            matches.append(PatternMatch("shooting_star", timestamp, bullish=False))

    index = df.index
    for i in range(1, len(df)):
        prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
        open_, close = df["open"].iloc[i], df["close"].iloc[i]
        timestamp = index[i]

        if _is_bullish_engulfing(prev_open, prev_close, open_, close):
            matches.append(PatternMatch("bullish_engulfing", timestamp, bullish=True))
        if _is_bearish_engulfing(prev_open, prev_close, open_, close):
            matches.append(PatternMatch("bearish_engulfing", timestamp, bullish=False))

    return matches
