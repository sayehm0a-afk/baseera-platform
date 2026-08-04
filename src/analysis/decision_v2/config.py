"""Every numeric constant Decision Engine V2 uses, in one place --
Phase 1 explicitly asks that scoring not "hide unexplained magic
numbers throughout the code." Mirrors the existing
`AIDecisionTuning`/`RecommendationTuning` pattern (frozen dataclass,
field defaults are the values used before this existed, environment-
independent -- calibration is a future backtesting concern, not an
env-var concern, matching how AIDecisionTuning itself is configured).

Thresholds that already have a canonical, configured home elsewhere
(minimum risk/reward, minimum liquidity, maximum data age) are read
from src.market_intelligence.config's existing getters, not
reinvented as a second, uncoordinated number.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionV2Tuning:
    # --- sub-score weights (must sum to 1.0; enforced by a test) -----
    trend_weight: float = 0.20
    momentum_weight: float = 0.15
    volume_weight: float = 0.10
    liquidity_weight: float = 0.10
    volatility_weight: float = 0.10
    risk_reward_weight: float = 0.15
    market_context_weight: float = 0.10
    data_quality_weight: float = 0.10

    # --- entry zone (ATR-based, matches AIDecisionEngine's own
    # ATR-percentage philosophy in _compute_price_targets) -----------
    entry_zone_atr_fraction: float = 0.35  # zone half-width = 0.35 * ATR%
    entry_zone_support_buffer_pct: float = 0.005  # matches AIDecisionEngine._LEVEL_BUFFER_PCT

    # --- how far past the entry zone counts as "missed" --------------
    # Once price has already captured this fraction of the total
    # stop-to-target distance, the entry zone's upper bound is capped
    # there -- a structural (stop/target-relative), not merely
    # price-relative, definition of "already ran too far to chase."
    missed_entry_reward_fraction: float = 0.5

    # --- extended targets ---------------------------------------------
    target_2_extra_atr_multiple: float = 1.5
    target_3_extra_atr_multiple: float = 1.5

    # --- volatility scoring bands (ATR as % of price) -----------------
    volatility_sweet_spot_low_pct: float = 0.015
    volatility_sweet_spot_high_pct: float = 0.045
    volatility_excessive_pct: float = 0.08

    # --- data quality / freshness --------------------------------------
    stale_data_penalty_score: float = 30.0  # data_quality_score ceiling once data is stale/prior-session
    missing_leg_penalty: float = 20.0  # per missing technical/fundamental leg

    # --- confidence capping --------------------------------------------
    market_closed_confidence_cap: float = 80.0
    missing_fundamentals_confidence_cap: float = 85.0
    thin_liquidity_confidence_cap: float = 70.0
    conflicting_indicators_confidence_cap: float = 65.0
    near_resistance_confidence_cap: float = 70.0
    missed_entry_confidence_cap: float = 60.0

    # --- holding period ranges (days), by horizon_type ------------------
    short_term_min_days: int = 1
    short_term_max_days: int = 15  # "من جلسة إلى 3 جلسات" .. up to ~3 weeks depending on conviction
    medium_term_min_days: int = 7
    medium_term_max_days: int = 90
    long_term_min_days: int = 30
    long_term_max_days: int = 180
