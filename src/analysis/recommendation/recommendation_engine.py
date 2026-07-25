"""RecommendationEngine: the orchestration layer that combines every
registered ScoreContributor's opinion into one final BUY/HOLD/SELL
call, a confidence score, and a human-readable explanation.

This is deliberately *not* a third analysis engine sitting next to
TechnicalAnalysisEngine/FundamentalAnalysisEngine -- it never computes
an indicator or a ratio, it only weighs and blends outputs those two
engines already produced (reused completely unmodified). Its own
extension point is the `contributors` list: `generate(context)` never
changes shape when a future module (news sentiment, insider trades,
macro indicators, an AI reasoning layer) is added -- that module is
just one more ScoreContributor passed into the constructor.
"""

from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.analysis.recommendation.fundamental_contributor import FundamentalScoreContributor
from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor
from src.analysis.recommendation.types import (
    AnalysisContext,
    Recommendation,
    RecommendationResult,
    RecommendationTuning,
    ScoreContribution,
    ScoreContributor,
    Signal,
)

_MAX_EXPLANATION_SIGNALS = 5


def _score_to_recommendation(score: float, tuning: RecommendationTuning) -> Recommendation:
    if score >= tuning.strong_buy_threshold:
        return Recommendation.STRONG_BUY
    if score >= tuning.buy_threshold:
        return Recommendation.BUY
    if score > tuning.sell_threshold:
        return Recommendation.HOLD
    if score > tuning.strong_sell_threshold:
        return Recommendation.SELL
    return Recommendation.STRONG_SELL


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _build_explanation(
    symbol: str,
    recommendation: Recommendation,
    confidence: float,
    final_score: float,
    technical_score: Optional[float],
    fundamental_score: Optional[float],
    contributions: Sequence[ScoreContribution],
) -> str:
    label = recommendation.value.replace("_", " ").title()
    parts = [f"{label} on {symbol}: weighted score {final_score:.1f}/100 (confidence {confidence:.1f}%)."]

    score_bits = []
    if technical_score is not None:
        score_bits.append(f"technical {technical_score:.1f}/100")
    if fundamental_score is not None:
        score_bits.append(f"fundamental {fundamental_score:.1f}/100")
    if score_bits:
        parts.append("Component scores: " + ", ".join(score_bits) + ".")

    unavailable = [c.source for c in contributions if c.score is None]
    if unavailable:
        parts.append(
            f"No {', '.join(unavailable)} data was available for this run, so the "
            "recommendation relies only on the remaining module(s)."
        )

    all_signals = [s for c in contributions for s in c.signals]
    influential = sorted((s for s in all_signals if s.impact != 0), key=lambda s: abs(s.impact), reverse=True)
    top_signals = influential[:_MAX_EXPLANATION_SIGNALS]
    if top_signals:
        parts.append("Key signals: " + "; ".join(s.description for s in top_signals) + ".")

    return " ".join(parts)


class RecommendationEngine:
    """Combines every registered ScoreContributor's output for one
    symbol into a single RecommendationResult.

    Defaults to the two M2.2/M2.3-backed contributors, each weighted
    50/50. Pass a custom `contributors` list to change weighting, drop
    a module, or add a new one (news sentiment, insider trades, macro
    indicators, AI reasoning, ...) -- `generate()`'s signature never
    changes. Pass a custom `tuning` (RecommendationTuning) to change
    the recommendation-band thresholds or the confidence agreement/
    disagreement heuristic without touching this class's code -- the
    Backtesting & Calibration Engine's extension point for calibrating
    *how* a blended score becomes a recommendation, distinct from
    *what* gets blended.
    """

    def __init__(
        self,
        contributors: Optional[List[ScoreContributor]] = None,
        tuning: Optional[RecommendationTuning] = None,
    ):
        self._contributors: List[ScoreContributor] = (
            list(contributors)
            if contributors is not None
            else [TechnicalScoreContributor(), FundamentalScoreContributor()]
        )
        self._tuning = tuning or RecommendationTuning()

    def generate(self, context: AnalysisContext, requesting_user_id: Optional[int] = None) -> RecommendationResult:
        """`requesting_user_id` is accepted for API-consistency with
        AnalystEngine.analyze()/AIDecisionEngine.decide() (Phase 10
        M10.8) but currently unused -- every registered ScoreContributor
        (technical/fundamental) is a deterministic calculation, not an
        LLM call, so there is nothing to attribute to a user or record
        as AI usage."""
        contributions = [c.contribute(context) for c in self._contributors]
        available = [c for c in contributions if c.score is not None and c.weight > 0]

        if not available:
            final_score = 50.0
            confidence = 0.0
        else:
            total_weight = sum(c.weight for c in available)
            final_score = sum(c.score * c.weight for c in available) / total_weight
            weighted_confidence = sum(c.confidence * c.weight for c in available) / total_weight

            total_possible_weight = sum(c.default_weight for c in self._contributors)
            coverage = total_weight / total_possible_weight if total_possible_weight > 0 else 0.0
            confidence = weighted_confidence * (coverage ** self._tuning.coverage_penalty_exponent)

            if len(available) >= 2:
                scores = [c.score for c in available]
                spread = max(scores) - min(scores)
                if spread <= self._tuning.agreement_spread_threshold:
                    confidence += self._tuning.agreement_bonus
                elif spread >= self._tuning.disagreement_spread_threshold:
                    confidence -= self._tuning.disagreement_penalty

            confidence = _clamp(confidence)

        final_score = _clamp(final_score)
        recommendation = _score_to_recommendation(final_score, self._tuning)

        technical_score = next((c.score for c in contributions if c.source == "technical"), None)
        fundamental_score = next((c.score for c in contributions if c.source == "fundamental"), None)

        explanation = _build_explanation(
            context.symbol, recommendation, confidence, final_score, technical_score, fundamental_score, contributions
        )

        signals: List[Signal] = [s for c in contributions for s in c.signals]

        return RecommendationResult(
            symbol=context.symbol,
            recommendation=recommendation,
            confidence=round(confidence, 1),
            explanation=explanation,
            technical_score=technical_score,
            fundamental_score=fundamental_score,
            final_score=round(final_score, 1),
            contributions=contributions,
            signals=signals,
            generated_at=datetime.now(timezone.utc),
        )
