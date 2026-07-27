"""CashManager: recommends a target cash-reserve band. Reads only
`AllocationBreakdown` (cash/total already computed by `AllocationEngine`)
and `PortfolioRiskProfile.risk_level` (already computed by `RiskEngine`,
reused, never recomputed) -- computes no price or score itself.
"""

from src.analysis.decision.types import RiskLevel
from src.portfolio_intelligence.config import (
    get_default_cash_target_pct_max,
    get_default_cash_target_pct_min,
    get_high_risk_cash_target_pct_max,
)
from src.portfolio_intelligence.types import AllocationBreakdown, CashRecommendation, PortfolioRiskProfile

_ELEVATED_RISK_LEVELS = {RiskLevel.HIGH, RiskLevel.VERY_HIGH}


class CashManager:
    def recommend(self, allocation: AllocationBreakdown, risk_profile: PortfolioRiskProfile) -> CashRecommendation:
        target_min = get_default_cash_target_pct_min()
        target_max = get_default_cash_target_pct_max()
        if risk_profile.risk_level in _ELEVATED_RISK_LEVELS:
            target_max = max(target_max, get_high_risk_cash_target_pct_max())

        within_band = target_min <= allocation.cash_weight <= target_max

        rationale = self._rationale(allocation, risk_profile, target_min, target_max, within_band)

        return CashRecommendation(
            current_cash=allocation.cash,
            current_cash_pct=round(allocation.cash_weight, 4),
            recommended_cash_pct_min=target_min,
            recommended_cash_pct_max=target_max,
            recommended_cash_amount_min=round(target_min * allocation.total_value, 2),
            recommended_cash_amount_max=round(target_max * allocation.total_value, 2),
            is_within_target_band=within_band,
            rationale=rationale,
        )

    @staticmethod
    def _rationale(
        allocation: AllocationBreakdown, risk_profile: PortfolioRiskProfile,
        target_min: float, target_max: float, within_band: bool,
    ) -> str:
        base = (
            f"Current cash is {allocation.cash_weight * 100:.1f}% of the portfolio "
            f"(target band: {target_min * 100:.0f}%-{target_max * 100:.0f}%"
        )
        risk_note = (
            f", widened for {risk_profile.risk_level.value.replace('_', ' ').title()} portfolio risk"
            if risk_profile.risk_level.value in ("HIGH", "VERY_HIGH") else ""
        )
        base += f"{risk_note})."
        if within_band:
            return base + " Cash reserve is within the recommended range."
        if allocation.cash_weight < target_min:
            return base + " Cash reserve is below the recommended minimum -- consider trimming a holding or holding proceeds from a future sale."
        return base + " Cash reserve is above the recommended maximum -- excess cash could be deployed into new or existing positions."
