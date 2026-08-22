"""Unit tests for breakout_confirmation.py -- Phase 3 area 5's real
breakout/false-breakout confirmation layer. Pure-function tests over
plain pandas DataFrames -- no DB, no mocking."""

import pandas as pd
import pytest

from src.analysis.decision_v2.breakout_confirmation import (
    BreakoutStatus,
    compute_breakout_confirmation,
)


def _df(closes, volumes=None):
    volumes = volumes if volumes is not None else [1_000] * len(closes)
    return pd.DataFrame({"close": closes, "volume": volumes})


def _volume_sma(values):
    return pd.Series(values)


def test_no_breakout_level_is_not_applicable():
    result = compute_breakout_confirmation(_df([10.0] * 10), breakout_level=None, volume_sma_20=None)
    assert result.status is BreakoutStatus.NOT_APPLICABLE
    assert result.level is None


def test_zero_or_negative_level_is_not_applicable():
    result = compute_breakout_confirmation(_df([10.0] * 10), breakout_level=0.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.NOT_APPLICABLE


def test_price_still_below_level_is_not_applicable():
    result = compute_breakout_confirmation(_df([9.0] * 10), breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.NOT_APPLICABLE


def test_empty_df_is_not_applicable():
    result = compute_breakout_confirmation(pd.DataFrame(columns=["close", "volume"]), breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.NOT_APPLICABLE


def test_cleared_level_but_too_few_bars_is_sequence_unverified():
    # Only 2 bars of history at all -- can't judge hold/failure.
    result = compute_breakout_confirmation(_df([10.5, 10.8]), breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.SEQUENCE_UNVERIFIED
    assert result.level == 10.0


def test_confirmed_breakout_held_three_days_with_volume():
    closes = [9.5, 9.8, 10.5, 10.6, 10.7]  # cleared 10.0 and held for 3 sessions
    volumes = [1_000, 1_000, 1_500, 1_400, 1_500]  # latest bar's volume elevated vs. its own 20-day average
    df = _df(closes, volumes)
    volume_sma_20 = _volume_sma([1_000, 1_000, 1_000, 1_000, 1_000])
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=volume_sma_20)
    assert result.status is BreakoutStatus.CONFIRMED_BREAKOUT
    assert result.hold_days == 3
    assert result.follow_through_pct == pytest.approx(7.0, abs=0.01)


def test_confirmed_hold_but_volume_not_confirmed_is_unconfirmed():
    closes = [9.5, 9.8, 10.5, 10.6, 10.7]
    volumes = [1_000, 1_000, 1_000, 1_000, 1_000]  # no volume surge at all
    df = _df(closes, volumes)
    volume_sma_20 = _volume_sma([1_000, 1_000, 1_000, 1_000, 1_000])
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=volume_sma_20)
    assert result.status is BreakoutStatus.UNCONFIRMED_BREAKOUT
    assert result.volume_confirmed is False


def test_early_breakout_meaningful_distance_but_short_hold():
    closes = [9.5, 9.8, 10.5]  # cleared today, only 1 session held
    df = _df(closes)
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.EARLY_BREAKOUT
    assert result.hold_days == 1
    assert result.volume_confirmed is None


def test_thin_clear_with_short_hold_is_unconfirmed():
    closes = [9.5, 9.8, 10.002]  # barely above the level -- noise-sized
    df = _df(closes)
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.UNCONFIRMED_BREAKOUT
    assert result.follow_through_pct < 0.3


def test_failed_breakout_reverted_after_clearing():
    closes = [9.5, 10.5, 10.6, 9.8]  # cleared, then closed back below the level
    df = _df(closes)
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.NOT_APPLICABLE  # latest close (9.8) is back below the level


def test_failed_breakout_reverted_then_recovered_above_again():
    # Cleared, reverted, then closed back above -- still a real prior
    # failure within the lookback window, must not be reported as a
    # clean confirmed/early breakout.
    closes = [9.5, 10.5, 10.6, 9.8, 10.2]
    df = _df(closes)
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=None)
    assert result.status is BreakoutStatus.FAILED_BREAKOUT


def test_hold_days_capped_at_lookback_window():
    closes = [10.5] * 15  # far more than LOOKBACK_DAYS=10 sessions above the level
    df = _df(closes)
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=None, lookback_days=10)
    assert result.status is BreakoutStatus.CONFIRMED_BREAKOUT
    assert result.hold_days == 10


def test_missing_volume_column_leaves_volume_confirmed_none():
    df = pd.DataFrame({"close": [9.5, 9.8, 10.5, 10.6, 10.7]})
    volume_sma_20 = _volume_sma([1_000] * 5)
    result = compute_breakout_confirmation(df, breakout_level=10.0, volume_sma_20=volume_sma_20)
    assert result.volume_confirmed is None
    assert result.status is BreakoutStatus.CONFIRMED_BREAKOUT
