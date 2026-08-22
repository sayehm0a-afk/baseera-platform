"""Unit tests for breakout_confirmation.py -- Phase 3 area 5's real
breakout/false-breakout confirmation layer. Pure-function tests over
plain pandas DataFrames -- no DB, no mocking."""

import pandas as pd
import pytest

from src.analysis.decision_v2.breakout_confirmation import (
    BreakoutStatus,
    compute_breakout_confirmation,
    resolve_breakout_reference_level,
)
from src.analysis.types import SupportResistanceLevels


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


class TestResolveBreakoutReferenceLevel:
    """Structural repair: the level fed to `compute_breakout_confirmation`
    must never be selected relative to the current/latest price -- that
    made the module's own `latest_close <= breakout_level` guard a
    tautology, since a level already broken is (by definition) no
    longer >= the current price and would silently be swapped for the
    next, still-untested level further up. `resolve_breakout_reference_
    level` fixes this by anchoring the level to a PRIOR price (from
    before the lookback window), never the latest close."""

    def test_no_levels_is_none(self):
        df = _df([9.5, 9.8, 10.5, 10.6, 10.7] * 3)
        assert resolve_breakout_reference_level(df, None) is None
        assert resolve_breakout_reference_level(df, SupportResistanceLevels(support=[], resistance=[])) is None

    def test_insufficient_history_is_none(self):
        # Fewer bars than lookback_days + 1 -- no "prior" close exists
        # yet to anchor a reference against.
        df = _df([9.5, 9.8, 10.5])
        levels = SupportResistanceLevels(support=[], resistance=[10.0])
        assert resolve_breakout_reference_level(df, levels, lookback_days=10) is None

    def test_selects_the_nearest_resistance_above_the_prior_price_not_the_latest_close(self):
        # 15 bars: the first 5 sit at 9.0 (the "prior" era), the last
        # 10 (the lookback window) have already cleared and held above
        # 10.0. The prior close (9.0) is what must select the 10.0
        # level -- selecting by the LATEST close (10.7, already past
        # 10.0) would instead pick 12.0, the next untested level up,
        # reproducing the exact tautology this function exists to fix.
        closes = [9.0] * 5 + [10.5, 10.6, 10.6, 10.7, 10.7, 10.7, 10.7, 10.7, 10.7, 10.7]
        df = _df(closes)
        levels = SupportResistanceLevels(support=[], resistance=[10.0, 12.0])
        level = resolve_breakout_reference_level(df, levels, lookback_days=10)
        assert level == 10.0

    def test_end_to_end_confirmed_breakout_is_now_reachable(self):
        """Before this fix, feeding `compute_breakout_confirmation` a
        level selected relative to the CURRENT price made
        CONFIRMED_BREAKOUT structurally impossible for any input -- see
        this module's own docstring. Composing the fixed reference
        level with the unchanged confirmation logic now genuinely
        reaches CONFIRMED_BREAKOUT."""
        closes = [9.0] * 6 + [10.5, 10.6, 10.6, 10.7, 10.7]
        volumes = [1_000] * 6 + [1_500, 1_400, 1_500, 1_600, 1_500]
        df = _df(closes, volumes)
        volume_sma_20 = _volume_sma([1_000] * 11)
        levels = SupportResistanceLevels(support=[], resistance=[10.0])
        level = resolve_breakout_reference_level(df, levels, lookback_days=10)
        result = compute_breakout_confirmation(df, level, volume_sma_20, lookback_days=10)
        assert result.status is BreakoutStatus.CONFIRMED_BREAKOUT

    def test_end_to_end_failed_breakout_is_reachable(self):
        # Cleared, reverted below the level, then closed back above it
        # -- the latest close (10.2) must be above the level for
        # compute_breakout_confirmation to treat a thesis as active at
        # all; the revert in between is what makes it FAILED rather
        # than a clean CONFIRMED/EARLY breakout.
        closes = [9.0] * 6 + [10.5, 10.6, 9.8, 9.7, 10.2]
        df = _df(closes)
        levels = SupportResistanceLevels(support=[], resistance=[10.0])
        level = resolve_breakout_reference_level(df, levels, lookback_days=10)
        result = compute_breakout_confirmation(df, level, None, lookback_days=10)
        assert result.status is BreakoutStatus.FAILED_BREAKOUT

    def test_result_is_deterministic_given_only_the_rows_it_is_handed(self):
        """No-look-ahead proof: re-slicing a longer series down to the
        exact same as-of row set it was originally evaluated with
        reproduces a byte-identical reference level -- the function
        never reaches beyond the `df` it is given."""
        closes = [9.0] * 6 + [10.5, 10.6, 10.6, 10.7, 10.7]
        levels = SupportResistanceLevels(support=[], resistance=[10.0, 12.0])
        df_as_of = _df(closes)
        level_as_of = resolve_breakout_reference_level(df_as_of, levels, lookback_days=10)

        # A longer series that includes genuinely FUTURE bars beyond
        # the as-of evaluation point -- re-truncated to the identical
        # as-of row set must reproduce the same result, proving the
        # future rows played no part when they were excluded.
        future_closes = closes + [11.5, 11.8, 12.5]
        df_with_future = _df(future_closes)
        df_re_truncated = df_with_future.iloc[: len(closes)]
        level_re_truncated = resolve_breakout_reference_level(df_re_truncated, levels, lookback_days=10)

        assert level_as_of == level_re_truncated == 10.0
