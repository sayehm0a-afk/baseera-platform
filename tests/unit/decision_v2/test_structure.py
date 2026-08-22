from src.analysis.decision.types import TimeHorizon
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.structure import (
    compute_entry_zone,
    compute_extended_targets,
    compute_holding_period,
    price_has_missed_entry_zone,
    price_severely_missed_entry_zone,
)
from src.analysis.types import SupportResistanceLevels

TUNING = DecisionV2Tuning()


class TestEntryZone:
    def test_hold_direction_has_no_entry_zone(self):
        low, high, basis = compute_entry_zone(100.0, 0.02, 0, 94.0, 110.0, None, TUNING)
        assert low is None and high is None and basis == "not_applicable"

    def test_long_entry_zone_ordering_is_valid(self):
        low, high, basis = compute_entry_zone(100.0, 0.02, 1, 94.0, 110.0, None, TUNING)
        assert low is not None and high is not None
        assert low <= high
        assert basis == "atr_band"

    def test_long_entry_zone_snaps_to_nearby_support(self):
        sr = SupportResistanceLevels(support=[99.5], resistance=[110.0])
        low, high, basis = compute_entry_zone(100.0, 0.02, 1, 94.0, 110.0, sr, TUNING)
        assert basis == "support_level"
        assert low > 99.5  # buffered just above the real support level

    def test_missing_atr_falls_back_to_a_conservative_default(self):
        low, high, basis = compute_entry_zone(100.0, None, 1, 94.0, 110.0, None, TUNING)
        assert low is not None and high is not None

    def test_high_is_capped_by_reward_already_captured_not_by_price_alone(self):
        # stop=94, target=110 -> total distance 16; 50% captured at 102.
        # A tiny ATR band around price=100 would otherwise put the ATR
        # ceiling near 100.3 (tighter than the reward cutoff here), so
        # this asserts the *tighter* of the two bounds wins, not price alone.
        low, high, basis = compute_entry_zone(100.0, 0.01, 1, 94.0, 110.0, None, TUNING)
        assert high <= 102.0 + 0.01  # never exceeds the 50%-of-reward cutoff by more than rounding

    def test_missing_stop_and_target_falls_back_to_pure_atr_band(self):
        low, high, basis = compute_entry_zone(100.0, 0.02, 1, None, None, None, TUNING)
        assert low is not None and high is not None and low <= high


class TestMissedEntry:
    def test_price_above_zone_high_is_missed(self):
        assert price_has_missed_entry_zone(105.0, 101.0, 1) is True

    def test_price_within_zone_is_not_missed(self):
        assert price_has_missed_entry_zone(100.0, 101.0, 1) is False

    def test_hold_direction_is_never_missed(self):
        assert price_has_missed_entry_zone(105.0, 101.0, 0) is False


class TestSeverelyMissedEntry:
    """Anti-chase structural repair: `price_severely_missed_entry_zone`
    is a magnitude-aware split of an overrun that has already tripped
    `price_has_missed_entry_zone` -- moderate overrun stays a live
    WAIT_FOR_PULLBACK setup, severe overrun becomes a genuinely
    MISSED_ENTRY one. Zone width here is 101.0 - 99.0 = 2.0."""

    def test_price_within_zone_is_not_severely_missed(self):
        assert price_severely_missed_entry_zone(100.0, 99.0, 101.0, 1) is False

    def test_moderate_overrun_is_not_severely_missed(self):
        # 101.5 is only 0.5 past the zone high -- well under one more
        # zone-width (2.0) beyond it.
        assert price_severely_missed_entry_zone(101.5, 99.0, 101.0, 1) is False

    def test_severe_overrun_is_severely_missed(self):
        # 103.5 is 2.5 past the zone high -- more than one more
        # zone-width (2.0) beyond it.
        assert price_severely_missed_entry_zone(103.5, 99.0, 101.0, 1) is True

    def test_exactly_one_zone_width_past_is_not_yet_severe(self):
        # Exactly at the boundary (101.0 + 2.0 = 103.0) -- strictly
        # greater than is required, not equal to.
        assert price_severely_missed_entry_zone(103.0, 99.0, 101.0, 1) is False

    def test_degenerate_zero_width_zone_any_overrun_is_severe(self):
        assert price_severely_missed_entry_zone(101.5, 101.0, 101.0, 1) is True

    def test_hold_direction_is_never_severely_missed(self):
        assert price_severely_missed_entry_zone(105.0, 99.0, 101.0, 0) is False

    def test_missing_inputs_are_never_severely_missed(self):
        assert price_severely_missed_entry_zone(None, 99.0, 101.0, 1) is False
        assert price_severely_missed_entry_zone(105.0, None, 101.0, 1) is False
        assert price_severely_missed_entry_zone(105.0, 99.0, None, 1) is False

    def test_both_missed_functions_agree_on_the_moderate_overrun_case(self):
        """The exact case that used to be a logical contradiction: any
        overrun at all makes `price_has_missed_entry_zone` True (and
        so reaches `Decision.WAIT_FOR_ENTRY` via Gate 15), while a
        moderate overrun keeps `price_severely_missed_entry_zone`
        False -- these two are now genuinely independent signals, not
        the same boolean asked to mean two contradictory things."""
        price, low, high, direction = 101.5, 99.0, 101.0, 1
        assert price_has_missed_entry_zone(price, high, direction) is True
        assert price_severely_missed_entry_zone(price, low, high, direction) is False


class TestExtendedTargets:
    def test_no_target_1_means_no_extended_targets(self):
        t2, t3, b2, b3 = compute_extended_targets(100.0, None, 2.0, 1, None, TUNING)
        assert t2 is None and t3 is None

    def test_atr_extension_when_no_resistance_available(self):
        t2, t3, b2, b3 = compute_extended_targets(100.0, 110.0, 2.0, 1, None, TUNING)
        assert t2 is not None
        assert t2 > 110.0
        assert b2 == "atr_extension"

    def test_real_resistance_beyond_target_1_is_preferred_over_atr(self):
        sr = SupportResistanceLevels(support=[], resistance=[115.0, 130.0])
        t2, t3, b2, b3 = compute_extended_targets(100.0, 110.0, 2.0, 1, sr, TUNING)
        assert t2 == 115.0
        assert b2 == "resistance_level"
        assert t3 == 130.0
        assert b3 == "resistance_level"

    def test_targets_stay_ordered(self):
        t2, t3, _, _ = compute_extended_targets(100.0, 110.0, 2.0, 1, None, TUNING)
        assert t2 > 110.0
        if t3 is not None:
            assert t3 > t2


class TestHoldingPeriod:
    def test_short_term_range(self):
        min_days, max_days, label = compute_holding_period(TimeHorizon.SHORT_TERM, TUNING)
        assert min_days < max_days
        assert "جلسة" in label

    def test_medium_term_range(self):
        min_days, max_days, label = compute_holding_period(TimeHorizon.MEDIUM_TERM, TUNING)
        assert min_days < max_days
        assert "أسبوع" in label

    def test_long_term_range(self):
        min_days, max_days, label = compute_holding_period(TimeHorizon.LONG_TERM, TUNING)
        assert min_days < max_days
        assert "شهر" in label
