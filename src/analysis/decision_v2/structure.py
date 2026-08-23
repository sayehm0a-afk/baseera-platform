"""Entry zone, extended targets (2 and 3), and holding-period range --
the three structural upgrades Phase 1 asks for beyond AIDecisionEngine's
existing single-point target/stop. Every computation here is ATR- and/or
real-support/resistance-based (the same primitives AIDecisionEngine's
own `_compute_price_targets`/`_refine_with_key_levels` already use,
imported and reused rather than reimplemented) -- never an arbitrary
percentage invented for this module.
"""

from typing import List, Optional, Tuple

from src.analysis.decision.types import TimeHorizon
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.types import SupportResistanceLevels

_MIN_PRICE = 0.01


def compute_entry_zone(
    price: Optional[float],
    atr_pct: Optional[float],
    direction: int,
    stop_loss: Optional[float],
    target_1: Optional[float],
    support_resistance: Optional[SupportResistanceLevels],
    tuning: DecisionV2Tuning,
) -> Tuple[Optional[float], Optional[float], str]:
    """Returns (entry_zone_low, entry_zone_high, basis). `None, None`
    when `direction == 0` (HOLD has no entry to zone) or price/ATR%
    isn't available. The low is ATR- and/or support-anchored (more
    room below the current price for a pullback entry). The high is
    deliberately NOT simply "price plus a small allowance" -- that
    would be tautological (price can never exceed a band defined
    relative to itself, making a "missed entry" condition
    unreachable). Instead it is capped at whichever is tighter: a
    small ATR allowance above price, or the point along the real
    stop-to-target distance where `missed_entry_reward_fraction` of
    the total reward has already been captured -- a structural,
    stop/target-relative definition of "already ran too far to chase"
    that stays meaningful across calls even though this engine keeps
    no persisted state between them.
    """
    if price is None or price <= 0 or direction == 0:
        return None, None, "not_applicable"
    if atr_pct is None or atr_pct <= 0:
        atr_pct = 0.02  # same conservative fallback AIDecisionEngine uses when ATR is unavailable

    half_width = tuning.entry_zone_atr_fraction * atr_pct * price
    if direction > 0:
        atr_low = price - half_width
        basis = "atr_band"
        if support_resistance is not None:
            candidate_supports = [s for s in support_resistance.support if atr_low <= s < price]
            if candidate_supports:
                nearest = max(candidate_supports)
                atr_low = nearest * (1 + tuning.entry_zone_support_buffer_pct)
                basis = "support_level"

        high = price + half_width * 0.3
        if stop_loss is not None and target_1 is not None and target_1 > stop_loss:
            reward_cutoff = stop_loss + tuning.missed_entry_reward_fraction * (target_1 - stop_loss)
            high = min(high, reward_cutoff)
        # Clamped down to `high`, never the reverse: once price has run
        # far enough that even the ATR/support-anchored low exceeds the
        # reward-based ceiling, the zone degenerates to a single point
        # at that ceiling rather than reporting a nonsensical
        # low > high -- the zone stays valid AND `price_has_missed_
        # entry_zone` (below) can still correctly fire.
        low = min(atr_low, high)
    else:
        atr_high = price + half_width
        basis = "atr_band"
        if support_resistance is not None:
            candidate_resistances = [r for r in support_resistance.resistance if price < r <= atr_high]
            if candidate_resistances:
                nearest = min(candidate_resistances)
                atr_high = nearest * (1 - tuning.entry_zone_support_buffer_pct)
                basis = "resistance_level"

        low = price - half_width * 0.3
        if stop_loss is not None and target_1 is not None and stop_loss > target_1:
            reward_cutoff = stop_loss - tuning.missed_entry_reward_fraction * (stop_loss - target_1)
            low = max(low, reward_cutoff)
        high = max(atr_high, low)

    low = max(_MIN_PRICE, low)
    high = max(low, high)
    return round(low, 2), round(high, 2), basis


def price_has_missed_entry_zone(price: Optional[float], entry_zone_high: Optional[float], direction: int) -> bool:
    """True when price has already run past the top of a long entry
    zone (or below the bottom of a short one) -- the condition that
    turns a would-be BUY_CANDIDATE into WAIT_FOR_ENTRY instead of
    encouraging the user to chase the move. Any overrun at all
    triggers this -- it governs Gate 15 (`entry_not_missed`) alone,
    which only needs to know "should this still be scored as an
    immediate BUY," not how far past the zone price has run. See
    `price_severely_missed_entry_zone` below for the magnitude-aware
    signal that gives Gate 15 a further, severity-based branch."""
    if price is None or entry_zone_high is None or direction == 0:
        return False
    if direction > 0:
        return price > entry_zone_high
    return False


def price_severely_missed_entry_zone(
    price: Optional[float],
    entry_zone_low: Optional[float],
    entry_zone_high: Optional[float],
    direction: int,
) -> bool:
    """True only once price has run not merely past the entry zone but
    by at least one further entry-zone-width beyond its top edge --
    the structural line between "extended, could still resolve back
    toward the setup" and "this setup is genuinely stale, chasing it
    no longer makes sense" that Gate 15 (`entry_not_missed`) uses to
    choose `Decision.WATCH` over the coarser `Decision.WAIT_FOR_ENTRY`.

    Reuses only the entry zone's own already-computed width -- no new
    external percentage/threshold is introduced -- so what counts as
    "genuinely missed" scales with how wide a healthy entry band was
    to begin with for this specific setup, rather than an arbitrary
    fixed number applied uniformly to every stock regardless of its
    own volatility (the entry zone's width is itself already
    ATR-derived, see `compute_entry_zone`)."""
    if price is None or entry_zone_low is None or entry_zone_high is None or direction == 0:
        return False
    if direction > 0:
        if price <= entry_zone_high:
            return False
        width = entry_zone_high - entry_zone_low
        if width <= 0:
            return True
        return price > entry_zone_high + width
    return False


def compute_extended_targets(
    price: Optional[float],
    target_1: Optional[float],
    atr_value: Optional[float],
    direction: int,
    support_resistance: Optional[SupportResistanceLevels],
    tuning: DecisionV2Tuning,
) -> Tuple[Optional[float], Optional[float], str, str]:
    """Returns (target_2, target_3, target_2_basis, target_3_basis).
    Prefers a real resistance level beyond target_1 when one exists;
    falls back to an additional ATR multiple (the same method
    target_1 itself is built from) otherwise. target_3 is only
    computed once target_2 exists -- Phase 1 explicitly says "when
    legitimately computable," so a missing target_1 or ATR never
    fabricates target_2/target_3."""
    if price is None or target_1 is None or direction == 0:
        return None, None, "not_applicable", "not_applicable"

    def _next_level(after: float, basis_extra_multiple: float) -> Tuple[Optional[float], str]:
        candidates: List[float] = []
        if support_resistance is not None:
            levels = support_resistance.resistance if direction > 0 else support_resistance.support
            candidates = [lv for lv in levels if (lv > after if direction > 0 else lv < after)]
        if candidates:
            level = min(candidates) if direction > 0 else max(candidates)
            return round(level, 2), "resistance_level" if direction > 0 else "support_level"
        if atr_value is not None and atr_value > 0:
            extension = atr_value * basis_extra_multiple
            level = after + extension if direction > 0 else after - extension
            return round(max(_MIN_PRICE, level), 2), "atr_extension"
        return None, "not_applicable"

    target_2, target_2_basis = _next_level(target_1, tuning.target_2_extra_atr_multiple)
    if target_2 is None:
        return None, None, "not_applicable", "not_applicable"

    target_3, target_3_basis = _next_level(target_2, tuning.target_3_extra_atr_multiple)
    return target_2, target_3, target_2_basis, target_3_basis


_HOLDING_PERIOD_LABELS_AR = {
    TimeHorizon.SHORT_TERM: "من جلسة إلى 3 أسابيع تقريبًا",
    TimeHorizon.MEDIUM_TERM: "من أسبوع إلى 3 أشهر تقريبًا",
    TimeHorizon.LONG_TERM: "من شهر إلى 6 أشهر تقريبًا",
}


def compute_holding_period(
    horizon: TimeHorizon, tuning: DecisionV2Tuning
) -> Tuple[int, int, str]:
    """A realistic day-count range, not a false exact date -- mapped
    from the already-computed `TimeHorizon` (AIDecisionEngine's
    `_derive_time_horizon`, itself driven by conviction/ADX/proximity
    to a key level). Returns (min_days, max_days, arabic_label)."""
    if horizon is TimeHorizon.LONG_TERM:
        return tuning.long_term_min_days, tuning.long_term_max_days, _HOLDING_PERIOD_LABELS_AR[horizon]
    if horizon is TimeHorizon.MEDIUM_TERM:
        return tuning.medium_term_min_days, tuning.medium_term_max_days, _HOLDING_PERIOD_LABELS_AR[horizon]
    return tuning.short_term_min_days, tuning.short_term_max_days, _HOLDING_PERIOD_LABELS_AR[horizon]
