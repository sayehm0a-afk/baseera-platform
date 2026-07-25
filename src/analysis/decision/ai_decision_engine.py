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

from src.analysis.decision.contributors.external_factor_contributors import (
    InsiderTransactionScoreContributor,
    MacroEconomicScoreContributor,
    NewsSentimentScoreContributor,
    SectorRotationScoreContributor,
)
from src.analysis.decision.contributors.momentum_contributor import MomentumScoreContributor
from src.analysis.decision.contributors.risk_contributor import RiskScoreContributor
from src.analysis.decision.contributors.volume_contributor import VolumeScoreContributor
from src.analysis.decision.types import (
    AIDecisionTuning,
    DecisionFactorBreakdown,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.recommendation.fundamental_contributor import FundamentalScoreContributor
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor
from src.analysis.recommendation.types import AnalysisContext, Recommendation, ScoreContribution

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
    list) can reuse it instead of re-deriving the same nine
    instances."""
    return [
        TechnicalScoreContributor(weight=0.25),
        FundamentalScoreContributor(weight=0.25),
        MomentumScoreContributor(weight=0.15),
        VolumeScoreContributor(weight=0.10),
        RiskScoreContributor(weight=0.10),
        NewsSentimentScoreContributor(weight=0.05),
        MacroEconomicScoreContributor(weight=0.05),
        InsiderTransactionScoreContributor(weight=0.03),
        SectorRotationScoreContributor(weight=0.02),
    ]


def _price_reference(context: AnalysisContext) -> Optional[float]:
    if context.latest_price is not None:
        return context.latest_price
    if context.technical_result is not None:
        bollinger_latest = context.technical_result.indicators["bollinger"].latest()
        if bollinger_latest:
            return bollinger_latest.get("middle")
    return None


def _compute_price_targets(
    final_score: float, price: Optional[float], atr_value: Optional[float], tuning: AIDecisionTuning
):
    if price is None or price <= 0:
        return None, None, None

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

    stop_loss = max(_MIN_PRICE, stop_loss)
    target_price = max(_MIN_PRICE, target_price)
    expected_return_pct = (target_price - price) / price * 100.0
    return target_price, stop_loss, expected_return_pct


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


def _derive_time_horizon(final_score: float, technical_result, tuning: AIDecisionTuning) -> TimeHorizon:
    conviction = abs(final_score - 50.0)
    adx = technical_result.indicators["adx_14"].latest() if technical_result is not None else None

    if conviction >= tuning.time_horizon_long_conviction_threshold and adx is not None and adx >= tuning.time_horizon_long_adx_threshold:
        return TimeHorizon.LONG_TERM
    if conviction >= tuning.time_horizon_medium_conviction_threshold:
        return TimeHorizon.MEDIUM_TERM
    return TimeHorizon.SHORT_TERM


def _derive_position_size(recommendation: Recommendation, confidence: float, risk_level: RiskLevel) -> PositionSize:
    idx = _SIZE_ORDER.index(_BASE_POSITION_SIZE[recommendation])
    if confidence < 50.0:
        idx -= 1
    if risk_level in (RiskLevel.HIGH, RiskLevel.VERY_HIGH):
        idx -= 1
    if risk_level is RiskLevel.VERY_HIGH:
        idx -= 1
    idx = max(0, idx)
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

    def decide(self, context: AnalysisContext) -> InvestmentDecision:
        result = self._recommendation_engine.generate(context)

        price = _price_reference(context)
        atr_value = (
            context.technical_result.indicators["atr_14"].latest() if context.technical_result is not None else None
        )
        target_price, stop_loss, expected_return_pct = _compute_price_targets(
            result.final_score, price, atr_value, self._tuning
        )

        risk_level = _derive_risk_level(result.contributions, self._tuning)
        time_horizon = _derive_time_horizon(result.final_score, context.technical_result, self._tuning)
        position_size = _derive_position_size(result.recommendation, result.confidence, risk_level)
        reasons = _build_reasons(
            context.symbol, result.recommendation, result.final_score, result.confidence,
            result.contributions, risk_level, position_size,
        )
        breakdown = [_to_breakdown(c) for c in result.contributions]

        return InvestmentDecision(
            symbol=result.symbol,
            recommendation=result.recommendation,
            confidence=result.confidence,
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
        )
