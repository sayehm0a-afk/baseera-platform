"""Unit tests for src.analysis.price_action.candlestick_patterns.

Each test constructs a small, deliberately-shaped OHLC bar (or bar
pair) that should or should not trigger a specific pattern, verified
against the documented geometric definition by hand.
"""

import pandas as pd

from src.analysis.price_action.candlestick_patterns import detect_patterns


def _df(rows):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close", "volume"])


def _names(matches):
    return {m.pattern_name for m in matches}


def test_doji_detected():
    # body=0.05, range=2 -> ratio 0.025 <= 0.1
    df = _df([[100, 101, 99, 100.05, 1000]])
    matches = detect_patterns(df)
    assert "doji" in _names(matches)
    doji = [m for m in matches if m.pattern_name == "doji"][0]
    assert bool(doji.bullish) is True
    assert doji.timestamp == df.index[0]


def test_hammer_detected():
    # body=1, lower_wick=3 (>=2*body), upper_wick=0.2 (<=body)
    df = _df([[102, 103.2, 99, 103, 1000]])
    matches = detect_patterns(df)
    assert "hammer" in _names(matches)


def test_shooting_star_detected():
    # body=1, upper_wick=4 (>=2*body), lower_wick=0.2 (<=body)
    df = _df([[100, 104, 98.8, 99, 1000]])
    matches = detect_patterns(df)
    assert "shooting_star" in _names(matches)


def test_bullish_engulfing_detected():
    df = _df(
        [
            [105, 106, 99, 100, 1000],  # bearish prev bar
            [99, 108, 98, 107, 1200],  # bullish bar that engulfs it
        ]
    )
    matches = detect_patterns(df)
    assert "bullish_engulfing" in _names(matches)
    match = [m for m in matches if m.pattern_name == "bullish_engulfing"][0]
    assert match.bullish is True
    assert match.timestamp == df.index[1]


def test_bearish_engulfing_detected():
    df = _df(
        [
            [100, 106, 99, 105, 1000],  # bullish prev bar
            [106, 107, 98, 99, 1200],  # bearish bar that engulfs it
        ]
    )
    matches = detect_patterns(df)
    assert "bearish_engulfing" in _names(matches)
    match = [m for m in matches if m.pattern_name == "bearish_engulfing"][0]
    assert match.bullish is False
    assert match.timestamp == df.index[1]


def test_ordinary_bar_matches_nothing():
    # body=1, range=2.5: not a doji (ratio 0.4); wicks too short for
    # hammer/shooting star.
    df = _df([[100, 102, 99.5, 101, 1000]])
    matches = detect_patterns(df)
    assert matches == []


def test_flat_bar_no_range_is_not_doji():
    # open == high == low == close -> zero range, explicitly excluded
    df = _df([[100, 100, 100, 100, 1000]])
    matches = detect_patterns(df)
    assert "doji" not in _names(matches)


def test_detect_patterns_returns_empty_list_for_empty_dataframe():
    df = _df([])
    assert detect_patterns(df) == []


def test_single_bar_can_match_multiple_patterns():
    # A very small-bodied bar that also has a long lower wick will
    # register as both a doji and a hammer -- both should be reported.
    df = _df([[100, 100.08, 97, 100.05, 1000]])
    matches = detect_patterns(df)
    names = _names(matches)
    assert "doji" in names
    assert "hammer" in names
