"""AIDecisionEngine: the AI Decision Intelligence Layer's orchestrator.

Sits above TechnicalAnalysisEngine, FundamentalAnalysisEngine, and
RecommendationEngine (which already includes confidence scoring) by
calling `RecommendationEngine.generate()` as a black box -- it is not
a parallel scoring engine and duplicates none of that blending/
confidence math. `RecommendationEngine` is configured here with an
expanded contributor list (the two existing modules plus five new
ones: Momentum, Volume, Risk, News, Macro, Insider Transactions,
Sector Rotation -- all satisfying the *same*, unmodified
`ScoreContributor` protocol `RecommendationEngine` already supported),
so every module this layer adds is exactly the extension point that
milestone was built for, not a new one.

What this layer adds that nothing else in the codebase produces: a
target price, a stop loss, a time horizon, an expected return, a risk
level, a position-size recommendation, plain-language reasons, and a
category-level explainable breakdown ("Technical Analysis: +35",
"Risk: -6", ...) -- all derived from `RecommendationResult` plus one
live price, never by recomputing anything the engines below already
computed.
"""

from datetime import datetime, timezone
from typing import List, Optional

from src.analysis.decision.contributors._series_utils import latest_value
from src.analysis.decision.contributors.external_factor_contributors import (
    InsiderTransactionScoreContributor,
    MacroEconomicScoreContributor,
    NewsSentimentScoreContributor,
    SectorRotationScoreContributor,
)
from src.analysis.decision.contributors.momentum_contributor import MomentumScoreContributor
from src.analysis.decision.contributors.price_structure_contributor import PriceStructureScoreContributor
from src.analysis.decision.contributors.risk_contributor import RiskScoreContributor
from src.analysis.decision.contributors.value_area_contributor import ValueAreaScoreContributor
from src.analysis.decision.contributors.volume_contributor import VolumeScoreContributor
from src.analysis.decision.types import (
    AIDecisionTuning,
    DecisionFactorBreakdown,
    EntryQuality,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.recommendation.fundamental_contributor import FundamentalScoreContributor
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor
from src.analysis.recommendation.types import AnalysisContext, Recommendation, ScoreContribution
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import FibonacciLevels, SupportResistanceLevels, VolumeProfileResult

_DEFAULT_ATR_PCT_FALLBACK = 0.02  # used only when ATR itself is unavailable but a price is
_MIN_PRICE = 0.01

# Recorded on every RecommendationSnapshot the Backtesting & Calibration
# Engine writes (src/backtesting/) -- bump this when a change to this
# module or RecommendationEngine would make an old snapshot's score no
# longer reproducible from its stored inputs, so an auditor can tell
# "this decision predates behavior change X."
ENGINE_VERSION = "1.0.0"

# Public (not module-private) so anything that needs to translate a
# ScoreContribution/Signal/DecisionFactorBreakdown "source" key into
# the same display label this module uses -- e.g.
# src.analysis.analyst.signal_interpreter, narrating the same
# breakdown this engine already produced -- can reuse it instead of
# redefining the same source-key-to-label mapping.
CATEGORY_LABELS = {
    "technical": "Technical Analysis",
    "fundamental": "Fundamental Analysis",
    "momentum": "Momentum",
    "volume": "Volume",
    "risk": "Risk",
    "price_structure": "Price Structure",
    "value_area": "Value Area",
    "news_sentiment": "News",
    "macro": "Macro",
    "insider_transactions": "Insider Transactions",
    "sector_rotation": "Sector Rotation",
}

_SIZE_ORDER = [PositionSize.NONE, PositionSize.SMALL, PositionSize.MODERATE, PositionSize.STANDARD, PositionSize.LARGE]
_BASE_POSITION_SIZE = {
    Recommendation.STRONG_BUY: PositionSize.LARGE,
    Recommendation.BUY: PositionSize.STANDARD,
    Recommendation.HOLD: PositionSize.NONE,
    Recommendation.SELL: PositionSize.STANDARD,
    Recommendation.STRONG_SELL: PositionSize.LARGE,
}

_MAX_REASON_SIGNALS = 6


def default_contributors() -> List:
    """The AI Decision Intelligence Layer's full contributor set.
    Weights sum to 1.0 and are deliberately different from
    RecommendationEngine's own 50/50 default (calibrated for exactly
    two contributors) -- Technical/Fundamental remain the two largest
    single weights, the rest are additive refinements. Public (not a
    module-private helper) so anything that needs AIDecisionEngine's
    default contributor set without also wanting its default tuning
    (e.g. src.backtesting.baselines.AIDecisionEngineStrategy, when a
    caller overrides RecommendationTuning but not the contributor
    list) can reuse it instead of re-deriving the same eleven
    instances.

    Phase 11: PriceStructureScoreContributor (Fibonacci +
    support/resistance) and ValueAreaScoreContributor (VWAP + Volume
    Profile) were added here -- every other weight was proportionally
    trimmed to keep the total at 1.0, rather than letting the new
    modules dilute the blend silently. Neither new module dominates:
    each caps out well below Technical/Fundamental's weight.
    """
    return [
        TechnicalScoreContributor(weight=0.22),
        FundamentalScoreContributor(weight=0.22),
        MomentumScoreContributor(weight=0.13),
        VolumeScoreContributor(weight=0.09),
        RiskScoreContributor(weight=0.10),
        PriceStructureScoreContributor(weight=0.08),
        ValueAreaScoreContributor(weight=0.05),
        NewsSentimentScoreContributor(weight=0.04),
        MacroEconomicScoreContributor(weight=0.04),
        InsiderTransactionScoreContributor(weight=0.02),
        SectorRotationScoreContributor(weight=0.01),
    ]


def _price_reference(context: AnalysisContext) -> Optional[float]:
    if context.latest_price is not None:
        return context.latest_price
    if context.technical_result is not None:
        bollinger_latest = context.technical_result.indicators["bollinger"].latest()
        if bollinger_latest:
            return bollinger_latest.get("middle")
    return None


_LEVEL_BUFFER_PCT = 0.005  # place the refined stop/target a hair beyond the level itself, not exactly on it


def _refine_with_key_levels(
    direction: int,
    price: float,
    stop_loss: float,
    target_price: float,
    support_resistance: Optional[SupportResistanceLevels],
) -> tuple:
    """Nudges the ATR-based stop/target toward a real, nearby
    support/resistance level when one sits inside the ATR-derived
    range. A stop placed just beyond an actual level the price has
    respected before is more defensible than an arbitrary ATR
    multiple, and a target capped just short of a level the price has
    struggled to clear before is more realistic than projecting
    straight through it. Returns (stop_loss, target_price, notes,
    stop_basis, target_basis) -- `notes` is empty and both bases are
    `"atr"` when no level fell inside the range (the pure ATR-based
    values are returned unchanged).

    A level within `_LEVEL_BUFFER_PCT` of `price` is excluded from
    target refinement entirely (root cause of the 2026-07-30 live scan
    defect: symbol 1020 was ranked TOP_BUY with an expected return of
    -0.16% because a resistance level 0.17% above price was capped by
    the buffer down to *below* price -- a BUY whose own target sits
    under its entry price. The buffer must never flip which side of
    `price` the target lands on; a level too close to leave room for
    the buffer is not usable as a target and the ATR-based target is
    kept instead).
    """
    notes: List[str] = []
    stop_basis = "atr"
    target_basis = "atr"
    if support_resistance is None:
        return stop_loss, target_price, notes, stop_basis, target_basis

    if direction > 0:
        candidate_supports = [s for s in support_resistance.support if stop_loss < s < price]
        if candidate_supports:
            nearest = max(candidate_supports)
            stop_loss = nearest * (1 - _LEVEL_BUFFER_PCT)
            stop_basis = "support_level"
            notes.append(f"stop loss tightened to just below the nearest support at {nearest:.2f}")

        candidate_resistances = [
            r for r in support_resistance.resistance
            if price < r < target_price and r * (1 - _LEVEL_BUFFER_PCT) > price
        ]
        if candidate_resistances:
            nearest = min(candidate_resistances)
            target_price = nearest * (1 - _LEVEL_BUFFER_PCT)
            target_basis = "resistance_level"
            notes.append(f"target price capped just below the nearest resistance at {nearest:.2f}")
    elif direction < 0:
        candidate_resistances = [r for r in support_resistance.resistance if price < r < stop_loss]
        if candidate_resistances:
            nearest = min(candidate_resistances)
            stop_loss = nearest * (1 + _LEVEL_BUFFER_PCT)
            stop_basis = "resistance_level"
            notes.append(f"stop loss tightened to just above the nearest resistance at {nearest:.2f}")

        candidate_supports = [
            s for s in support_resistance.support
            if target_price < s < price and s * (1 + _LEVEL_BUFFER_PCT) < price
        ]
        if candidate_supports:
            nearest = max(candidate_supports)
            target_price = nearest * (1 + _LEVEL_BUFFER_PCT)
            target_basis = "support_level"
            notes.append(f"target price capped just above the nearest support at {nearest:.2f}")

    return stop_loss, target_price, notes, stop_basis, target_basis


def _compute_price_targets(
    final_score: float,
    price: Optional[float],
    atr_value: Optional[float],
    tuning: AIDecisionTuning,
    support_resistance: Optional[SupportResistanceLevels] = None,
):
    if price is None or price <= 0:
        return None, None, None, [], "atr", "atr"

    atr_pct = (atr_value / price) if (atr_value is not None and atr_value > 0) else _DEFAULT_ATR_PCT_FALLBACK
    direction = 1 if final_score >= 50 else -1
    conviction = min(1.0, abs(final_score - 50) / 50.0)
    reward_multiple = tuning.base_reward_atr_multiple + tuning.max_extra_reward_atr_multiple * conviction

    stop_distance = atr_pct * tuning.stop_atr_multiple * price
    reward_distance = atr_pct * reward_multiple * price

    if direction > 0:
        stop_loss = price - stop_distance
        target_price = price + reward_distance
    else:
        stop_loss = price + stop_distance
        target_price = price - reward_distance

    stop_loss, target_price, notes, stop_basis, target_basis = _refine_with_key_levels(
        direction, price, stop_loss, target_price, support_resistance
    )

    stop_loss = max(_MIN_PRICE, stop_loss)
    target_price = max(_MIN_PRICE, target_price)
    expected_return_pct = (target_price - price) / price * 100.0
    return target_price, stop_loss, expected_return_pct, notes, stop_basis, target_basis


def _derive_risk_level(contributions: List[ScoreContribution], tuning: AIDecisionTuning) -> RiskLevel:
    risk_contribution = next((c for c in contributions if c.source == "risk"), None)
    if risk_contribution is None or risk_contribution.score is None:
        return RiskLevel.MEDIUM  # unknown risk defaults to a conservative middle, never LOW

    rs = risk_contribution.score
    if rs >= tuning.risk_low_threshold:
        return RiskLevel.LOW
    if rs >= tuning.risk_medium_threshold:
        return RiskLevel.MEDIUM
    if rs >= tuning.risk_high_threshold:
        return RiskLevel.HIGH
    return RiskLevel.VERY_HIGH


def _nearest_key_level_proximity(
    price: Optional[float],
    support_resistance: Optional[SupportResistanceLevels],
    fibonacci: Optional[FibonacciLevels],
) -> Optional[float]:
    """The smallest fractional distance from `price` to any detected
    support/resistance or Fibonacci level -- shared by
    `_derive_time_horizon` (a decision point right at hand argues for a
    short-term view over a multi-month hold) and `_derive_entry_quality`
    (the same proximity math PriceStructureScoreContributor already
    uses, reapplied here for a decision-layer fact rather than a score).
    """
    if price is None or price <= 0:
        return None

    levels: List[float] = []
    if support_resistance is not None:
        levels.extend(support_resistance.support)
        levels.extend(support_resistance.resistance)
    if fibonacci is not None:
        levels.extend(fibonacci.levels.values())
    if not levels:
        return None

    return min(abs(price - level) / price for level in levels)


def _derive_time_horizon(
    final_score: float,
    technical_result: Optional[TechnicalAnalysisResult],
    price: Optional[float],
    tuning: AIDecisionTuning,
) -> TimeHorizon:
    conviction = abs(final_score - 50.0)
    adx = technical_result.indicators["adx_14"].latest() if technical_result is not None else None

    support_resistance = technical_result.support_resistance if technical_result is not None else None
    fibonacci = technical_result.fibonacci_retracement if technical_result is not None else None
    proximity = _nearest_key_level_proximity(price, support_resistance, fibonacci)
    if proximity is not None and proximity <= tuning.key_level_proximity_threshold:
        # A real support/resistance/Fibonacci level sits right at the
        # current price -- the immediate move is likely to resolve at
        # that level one way or the other before a multi-month thesis
        # would have time to play out, so this caps the horizon at
        # SHORT_TERM regardless of how strong the underlying conviction
        # or trend strength otherwise looks.
        return TimeHorizon.SHORT_TERM

    if conviction >= tuning.time_horizon_long_conviction_threshold and adx is not None and adx >= tuning.time_horizon_long_adx_threshold:
        return TimeHorizon.LONG_TERM
    if conviction >= tuning.time_horizon_medium_conviction_threshold:
        return TimeHorizon.MEDIUM_TERM
    return TimeHorizon.SHORT_TERM


def _derive_entry_quality(
    direction: int,
    price: Optional[float],
    support_resistance: Optional[SupportResistanceLevels],
    fibonacci: Optional[FibonacciLevels],
    vwap_value: Optional[float],
    volume_profile: Optional[VolumeProfileResult],
    tuning: AIDecisionTuning,
) -> tuple:
    """How favorable *this specific price* is as an entry for the
    recommended direction -- reuses the same support/resistance/
    Fibonacci/VWAP/Volume-Profile facts PriceStructureScoreContributor
    and ValueAreaScoreContributor already score, applied here to a
    single decision-layer question (buy the dip vs. chase the rally)
    rather than to the blended score. Returns (EntryQuality, notes);
    notes is empty (and quality FAIR) when `price` or a recommendation
    direction is unavailable -- "not assessed," not a guess.
    """
    if price is None or price <= 0 or direction == 0:
        return EntryQuality.FAIR, []

    points = 0.0
    notes: List[str] = []

    if support_resistance is not None:
        if direction > 0:
            above = [r for r in support_resistance.resistance if r > price]
            if above:
                proximity = (min(above) - price) / price
                if proximity <= tuning.key_level_proximity_threshold:
                    points -= 15.0
                    notes.append(
                        f"buying just under resistance at {min(above):.2f} -- little room before "
                        "a likely rejection, a poor entry."
                    )
            below = [s for s in support_resistance.support if s < price]
            if below:
                proximity = (price - max(below)) / price
                if proximity <= tuning.key_level_proximity_threshold:
                    points += 15.0
                    notes.append(f"buying just above support at {max(below):.2f} -- a favorable, defensible entry.")
        else:
            below = [s for s in support_resistance.support if s < price]
            if below:
                proximity = (price - max(below)) / price
                if proximity <= tuning.key_level_proximity_threshold:
                    points -= 15.0
                    notes.append(
                        f"selling just above support at {max(below):.2f} -- little room before a "
                        "likely bounce, a poor entry."
                    )
            above = [r for r in support_resistance.resistance if r > price]
            if above:
                proximity = (min(above) - price) / price
                if proximity <= tuning.key_level_proximity_threshold:
                    points += 15.0
                    notes.append(f"selling just under resistance at {min(above):.2f} -- a favorable, defensible entry.")

    if fibonacci is not None and fibonacci.levels:
        nearest_name, nearest_price = min(fibonacci.levels.items(), key=lambda kv: abs(kv[1] - price))
        proximity = abs(price - nearest_price) / price
        if proximity <= tuning.key_level_proximity_threshold:
            favorable = (direction > 0 and fibonacci.is_uptrend) or (direction < 0 and not fibonacci.is_uptrend)
            if favorable:
                points += 10.0
                notes.append(f"entering near the {nearest_name}% Fibonacci retracement level -- good timing.")
            else:
                points -= 10.0
                notes.append(f"entering against the {nearest_name}% Fibonacci retracement level -- weaker timing.")

    if vwap_value is not None and vwap_value > 0:
        deviation = (price - vwap_value) / vwap_value
        extended = (direction > 0 and deviation >= 0.02) or (direction < 0 and deviation <= -0.02)
        if extended:
            points -= 10.0
            side = "above" if direction > 0 else "below"
            notes.append(f"price is already extended {side} its VWAP -- risk of chasing the move.")
        elif abs(deviation) < 0.01:
            points += 5.0
            notes.append("price sits close to VWAP -- a fair-value entry, not a chase.")

    if volume_profile is not None and volume_profile.point_of_control > 0:
        poc_deviation = (price - volume_profile.point_of_control) / volume_profile.point_of_control
        if abs(poc_deviation) < 0.02:
            points += 5.0
            notes.append("price sits near the volume profile's point of control -- an accepted, liquid price.")

    score = max(0.0, min(100.0, 50.0 + points))
    if score >= tuning.entry_quality_excellent_threshold:
        quality = EntryQuality.EXCELLENT
    elif score >= tuning.entry_quality_good_threshold:
        quality = EntryQuality.GOOD
    elif score >= tuning.entry_quality_fair_threshold:
        quality = EntryQuality.FAIR
    else:
        quality = EntryQuality.POOR

    return quality, notes


def _calibrate_confidence(
    confidence: float,
    direction: int,
    price: Optional[float],
    vwap_value: Optional[float],
    volume_profile: Optional[VolumeProfileResult],
    tuning: AIDecisionTuning,
) -> tuple:
    """A small adjustment layer on top of RecommendationEngine's own
    blended confidence -- two facts that blend never isolates on their
    own: whether price is trading on the "right side" of VWAP for the
    recommended direction (an intraday positioning signal), and whether
    price currently sits in a liquid (high relative volume) or thin
    (low relative volume) zone of the Volume Profile, since a thin zone
    means a real move can be sharper/less reliable than the blended
    score alone would suggest. Returns (confidence, notes); notes is
    empty when neither input was available.
    """
    if price is None or price <= 0 or direction == 0:
        return confidence, []

    notes: List[str] = []

    if vwap_value is not None and vwap_value > 0:
        aligned = (direction > 0 and price >= vwap_value) or (direction < 0 and price <= vwap_value)
        if aligned:
            confidence += tuning.vwap_confidence_adjustment
            notes.append(
                f"price is on the same side of VWAP ({vwap_value:.2f}) as the recommended direction -- "
                "intraday confidence boosted."
            )
        else:
            confidence -= tuning.vwap_confidence_adjustment
            notes.append(
                f"price is on the opposite side of VWAP ({vwap_value:.2f}) from the recommended direction -- "
                "intraday confidence reduced."
            )

    if volume_profile is not None and volume_profile.bin_volumes and volume_profile.bin_edges:
        edges = volume_profile.bin_edges
        volumes = volume_profile.bin_volumes
        bin_index = None
        for i in range(len(volumes)):
            if edges[i] <= price <= edges[i + 1]:
                bin_index = i
                break
        if bin_index is not None:
            average_volume = sum(volumes) / len(volumes)
            if average_volume > 0:
                ratio = volumes[bin_index] / average_volume
                if ratio <= tuning.liquidity_thin_zone_ratio:
                    confidence -= tuning.liquidity_confidence_adjustment
                    notes.append(
                        "price sits in a thin-volume zone of the volume profile -- liquidity confidence reduced."
                    )
                elif ratio >= tuning.liquidity_thick_zone_ratio:
                    confidence += tuning.liquidity_confidence_adjustment
                    notes.append(
                        "price sits in a high-volume (liquid) zone of the volume profile -- liquidity confidence boosted."
                    )

    return max(0.0, min(100.0, confidence)), notes


def _derive_position_size(
    recommendation: Recommendation,
    confidence: float,
    risk_level: RiskLevel,
    entry_quality: EntryQuality,
    risk_reward_ratio: Optional[float],
    tuning: AIDecisionTuning,
) -> PositionSize:
    idx = _SIZE_ORDER.index(_BASE_POSITION_SIZE[recommendation])
    if confidence < 50.0:
        idx -= 1
    if risk_level in (RiskLevel.HIGH, RiskLevel.VERY_HIGH):
        idx -= 1
    if risk_level is RiskLevel.VERY_HIGH:
        idx -= 1

    # Phase 11: a poor entry (chasing) or a weak reward-for-the-risk-taken
    # setup shrinks the size even when the score/risk-level alone looked
    # fine; a genuinely excellent entry with a strong reward:risk ratio
    # can offset one step of downgrade, but never overrides HOLD (idx=0
    # stays floored below) or pushes past what the recommendation itself
    # already earned.
    if entry_quality is EntryQuality.POOR:
        idx -= 1
    if risk_reward_ratio is not None and risk_reward_ratio < tuning.poor_risk_reward_threshold:
        idx -= 1
    if (
        recommendation is not Recommendation.HOLD
        and entry_quality is EntryQuality.EXCELLENT
        and risk_reward_ratio is not None
        and risk_reward_ratio >= tuning.excellent_risk_reward_threshold
    ):
        idx += 1

    idx = max(0, min(len(_SIZE_ORDER) - 1, idx))
    return _SIZE_ORDER[idx]


def _to_breakdown(contribution: ScoreContribution) -> DecisionFactorBreakdown:
    category = CATEGORY_LABELS.get(contribution.source, contribution.source.replace("_", " ").title())
    points = round(contribution.score - 50.0, 1) if contribution.score is not None else 0.0
    return DecisionFactorBreakdown(
        category=category,
        points=points,
        weight=contribution.weight,
        confidence=contribution.confidence,
        available=contribution.score is not None,
        notes=contribution.notes,
    )


def _build_reasons(
    symbol: str,
    recommendation: Recommendation,
    final_score: float,
    confidence: float,
    contributions: List[ScoreContribution],
    risk_level: RiskLevel,
    position_size: PositionSize,
) -> List[str]:
    label = recommendation.value.replace("_", " ").title()
    reasons = [f"{label} on {symbol}: final weighted score {final_score:.1f}/100 with {confidence:.1f}% confidence."]

    all_signals = [s for c in contributions for s in c.signals]
    influential = sorted((s for s in all_signals if s.impact != 0), key=lambda s: abs(s.impact), reverse=True)
    reasons.extend(s.description for s in influential[:_MAX_REASON_SIGNALS])

    unavailable = sorted({c.source for c in contributions if c.score is None})
    if unavailable:
        reasons.append(
            "The following modules had no data available for this run and did not influence the "
            f"decision: {', '.join(unavailable)}."
        )

    reasons.append(
        f"Risk assessed as {risk_level.value.title()}; sized as a {position_size.value.title()} position for a new entry."
    )
    return reasons


class AIDecisionEngine:
    """Produces one final `InvestmentDecision` per symbol. Pass a
    pre-configured `RecommendationEngine` (e.g. with a custom
    contributor list/weights, or extra modules beyond the default
    nine) to change what feeds the decision -- this class's own
    `decide()` signature never changes either way. Pass a custom
    `tuning` (AIDecisionTuning) to change ATR stop/reward multiples or
    risk-level thresholds without touching this class's code -- the
    Backtesting & Calibration Engine's extension point for this
    layer's own price-target/risk logic, distinct from
    RecommendationTuning (which governs the RecommendationEngine layer
    below it)."""

    def __init__(
        self,
        recommendation_engine: Optional[RecommendationEngine] = None,
        tuning: Optional[AIDecisionTuning] = None,
    ):
        self._recommendation_engine = recommendation_engine or RecommendationEngine(contributors=default_contributors())
        self._tuning = tuning or AIDecisionTuning()

    def decide(self, context: AnalysisContext, requesting_user_id: Optional[int] = None) -> InvestmentDecision:
        """`requesting_user_id` is accepted for API-consistency with
        AnalystEngine.analyze()/RecommendationEngine.generate() (Phase
        10 M10.8) but currently unused -- this engine makes no LLM
        call (it is a deterministic, weighted-contributor scoring
        engine; "AI" in its name refers to automated decision-making,
        not a generative model), so there is nothing to attribute to a
        user or record as AI usage."""
        result = self._recommendation_engine.generate(context, requesting_user_id=requesting_user_id)

        technical_result = context.technical_result
        price = _price_reference(context)
        atr_value = technical_result.indicators["atr_14"].latest() if technical_result is not None else None
        support_resistance = technical_result.support_resistance if technical_result is not None else None
        fibonacci = technical_result.fibonacci_retracement if technical_result is not None else None
        vwap_value = latest_value(technical_result.vwap_20) if technical_result is not None else None
        volume_profile = technical_result.volume_profile if technical_result is not None else None

        direction = 1 if result.final_score >= 50 else -1

        target_price, stop_loss, expected_return_pct, level_notes, stop_loss_basis, target_price_basis = (
            _compute_price_targets(result.final_score, price, atr_value, self._tuning, support_resistance)
        )

        risk_reward_ratio = None
        if target_price is not None and stop_loss is not None and price is not None:
            risk_distance = abs(price - stop_loss)
            if risk_distance > 0:
                risk_reward_ratio = round(abs(target_price - price) / risk_distance, 2)

        entry_quality, entry_quality_notes = _derive_entry_quality(
            direction, price, support_resistance, fibonacci, vwap_value, volume_profile, self._tuning
        )

        confidence, confidence_calibration_notes = _calibrate_confidence(
            result.confidence, direction, price, vwap_value, volume_profile, self._tuning
        )
        confidence = round(confidence, 1)

        risk_level = _derive_risk_level(result.contributions, self._tuning)
        time_horizon = _derive_time_horizon(result.final_score, technical_result, price, self._tuning)
        position_size = _derive_position_size(
            result.recommendation, confidence, risk_level, entry_quality, risk_reward_ratio, self._tuning
        )
        reasons = _build_reasons(
            context.symbol, result.recommendation, result.final_score, confidence,
            result.contributions, risk_level, position_size,
        )
        reasons.extend(level_notes)
        reasons.extend(entry_quality_notes)
        reasons.extend(confidence_calibration_notes)
        if risk_reward_ratio is not None:
            reasons.append(f"Risk/reward ratio: {risk_reward_ratio:.2f} (entry quality: {entry_quality.value.title()}).")
        breakdown = [_to_breakdown(c) for c in result.contributions]

        return InvestmentDecision(
            symbol=result.symbol,
            recommendation=result.recommendation,
            confidence=confidence,
            final_score=result.final_score,
            target_price=round(target_price, 2) if target_price is not None else None,
            stop_loss=round(stop_loss, 2) if stop_loss is not None else None,
            time_horizon=time_horizon,
            expected_return_pct=round(expected_return_pct, 2) if expected_return_pct is not None else None,
            risk_level=risk_level,
            position_size=position_size,
            reasons=reasons,
            breakdown=breakdown,
            signals=result.signals,
            generated_at=datetime.now(timezone.utc),
            entry_quality=entry_quality,
            entry_quality_notes=entry_quality_notes,
            risk_reward_ratio=risk_reward_ratio,
            stop_loss_basis=stop_loss_basis,
            target_price_basis=target_price_basis,
            confidence_calibration_notes=confidence_calibration_notes,
        )
