"""PositionSizer: maps one already-analyzed holding to a
increase/reduce/exit/hold action.

Reuses exactly two already-computed signals, never recomputes either:
`HoldingAnalysis.recommendation` (`AIDecisionEngine`, via
`AnalystEngine`) and `HoldingAnalysis.position_size` (the same
engine's own position-size band). `position_size` is compared against
a disclosed default target-weight table
(`config.get_target_weight_by_position_size`) purely to judge whether
the *current* holding is under- or over-sized relative to that band --
never to imply a specific dollar amount to trade.
"""

from src.analysis.recommendation.types import Recommendation
from src.portfolio_intelligence.config import (
    get_overweight_drift_threshold,
    get_position_concentration_threshold,
    get_target_weight_by_position_size,
    get_underweight_drift_threshold,
)
from src.portfolio_intelligence.types import HoldingAnalysis, PositionAction, RebalanceAction

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}


class PositionSizer:
    def size(self, holding: HoldingAnalysis) -> RebalanceAction:
        recommendation = holding.recommendation
        current_weight = holding.weight or 0.0

        if recommendation is Recommendation.STRONG_SELL:
            return self._action(holding, PositionAction.EXIT, f"{holding.symbol} is rated STRONG_SELL -- consider exiting the position.")

        if recommendation is Recommendation.SELL:
            return self._action(holding, PositionAction.REDUCE, f"{holding.symbol} is rated SELL -- consider reducing the position.")

        if recommendation in _BUY_LIKE:
            target_weight = get_target_weight_by_position_size().get(
                holding.position_size.value if holding.position_size else "NONE", 0.0
            )
            if current_weight < target_weight - get_underweight_drift_threshold():
                return self._action(
                    holding, PositionAction.INCREASE,
                    f"{holding.symbol} is rated {recommendation.value} with a current weight of "
                    f"{current_weight * 100:.1f}%, below its {target_weight * 100:.1f}% target band -- "
                    "consider increasing the position.",
                )
            if current_weight > target_weight + get_overweight_drift_threshold():
                return self._action(
                    holding, PositionAction.REDUCE,
                    f"{holding.symbol} is rated {recommendation.value} but is already {current_weight * 100:.1f}% of "
                    f"the portfolio, above its {target_weight * 100:.1f}% target band -- consider trimming to "
                    "manage concentration.",
                )
            return self._action(holding, PositionAction.HOLD, f"{holding.symbol} is rated {recommendation.value} and sized within its target band.")

        # HOLD (or an unrated holding) -- a risk-management override for an already-overweight position.
        if current_weight > get_position_concentration_threshold():
            return self._action(
                holding, PositionAction.REDUCE,
                f"{holding.symbol} is {current_weight * 100:.1f}% of the portfolio, above the "
                f"{get_position_concentration_threshold() * 100:.0f}% concentration threshold -- "
                "consider trimming regardless of its neutral rating.",
            )
        return self._action(holding, PositionAction.HOLD, f"{holding.symbol} is rated {recommendation.value if recommendation else 'unrated'} -- no action indicated.")

    @staticmethod
    def _action(holding: HoldingAnalysis, action: PositionAction, rationale: str) -> RebalanceAction:
        return RebalanceAction(
            symbol=holding.symbol,
            action=action,
            current_weight=holding.weight,
            rationale=rationale,
            recommendation=holding.recommendation.value if holding.recommendation else None,
            confidence=holding.confidence,
        )
