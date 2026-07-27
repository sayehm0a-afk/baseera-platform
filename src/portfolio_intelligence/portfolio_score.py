"""PortfolioScore: the 0-100 portfolio health score -- a disclosed,
configurable weighted blend of four already-computed components
(diversification, risk, cash adequacy, recommendation alignment).
Computes no new statistic; every input is read from
`DiversificationScore`/`PortfolioRiskProfile`/`CashRecommendation`
(all reused from their own dedicated engines) plus each holding's
already-computed recommendation.
"""

from typing import List

from src.portfolio_intelligence.config import get_health_score_weights
from src.portfolio_intelligence.types import (
    CashRecommendation,
    DiversificationScore,
    HealthBand,
    HoldingAnalysis,
    PortfolioHealthScore,
    PortfolioRiskProfile,
)

_FAVORABLE_RECOMMENDATIONS = {"STRONG_BUY", "BUY", "HOLD"}

_BAND_THRESHOLDS = (
    (85.0, HealthBand.EXCELLENT),
    (70.0, HealthBand.GOOD),
    (50.0, HealthBand.FAIR),
    (30.0, HealthBand.POOR),
)


def _band(score: float) -> HealthBand:
    for threshold, band in _BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return HealthBand.CRITICAL


def _cash_adequacy_component(cash_recommendation: CashRecommendation) -> float:
    if cash_recommendation.is_within_target_band:
        return 100.0
    band_width = max(cash_recommendation.recommended_cash_pct_max - cash_recommendation.recommended_cash_pct_min, 0.01)
    if cash_recommendation.current_cash_pct < cash_recommendation.recommended_cash_pct_min:
        deviation = cash_recommendation.recommended_cash_pct_min - cash_recommendation.current_cash_pct
    else:
        deviation = cash_recommendation.current_cash_pct - cash_recommendation.recommended_cash_pct_max
    return max(0.0, 100.0 - (deviation / band_width) * 100.0)


def _recommendation_alignment_component(holdings: List[HoldingAnalysis]) -> float:
    weighted_holdings = [h for h in holdings if h.available and h.weight is not None]
    total_weight = sum(h.weight for h in weighted_holdings)
    if total_weight <= 0:
        return 50.0  # no assessable holdings -- a neutral default, not fabricated confidence
    favorable_weight = sum(
        h.weight for h in weighted_holdings if h.recommendation is not None and h.recommendation.value in _FAVORABLE_RECOMMENDATIONS
    )
    return round(favorable_weight / total_weight * 100.0, 2)


class PortfolioScore:
    def compute(
        self,
        diversification: DiversificationScore,
        risk_profile: PortfolioRiskProfile,
        cash_recommendation: CashRecommendation,
        holdings: List[HoldingAnalysis],
    ) -> PortfolioHealthScore:
        weights = get_health_score_weights()

        components = {
            "diversification": round(diversification.score, 2),
            "risk": round(100.0 - risk_profile.risk_score, 2),
            "cash_adequacy": round(_cash_adequacy_component(cash_recommendation), 2),
            "recommendation_alignment": _recommendation_alignment_component(holdings),
        }

        score = round(sum(weights.get(key, 0.0) * value for key, value in components.items()), 2)
        band = _band(score)

        narrative = (
            f"Portfolio health score is {score:.1f}/100 ({band.value.title()}). "
            f"Diversification: {components['diversification']:.1f}/100. "
            f"Risk (inverted, higher is better): {components['risk']:.1f}/100. "
            f"Cash adequacy: {components['cash_adequacy']:.1f}/100. "
            f"Recommendation alignment: {components['recommendation_alignment']:.1f}/100."
        )

        return PortfolioHealthScore(score=score, band=band, components=components, narrative=narrative)
