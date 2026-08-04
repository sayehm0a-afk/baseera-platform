"""Phase 2A sections H (support/resistance) and I (liquidity/
accumulation). Computes no new indicator: support/resistance levels
come from `src.analysis.indicators.support_resistance` (swing-pivot/
fractal detection, already run by `TechnicalAnalysisEngine`); volume
figures come from the real quote/daily-bar payload
(`context.extra["quote"]["volume"]`) and the already-registered
`volume_sma_20` indicator.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.analysis.types import SupportResistanceLevels

_SUPPORT_RESISTANCE_EVIDENCE_AR = (
    "مستويات مكتشفة عبر تحليل القمم والقيعان السعرية (swing pivot) في البيانات "
    "التاريخية الحقيقية المتاحة -- المستوى «الأقرب» هو الأقرب لسعر السوق الحالي، "
    "و«الرئيسي» هو الأبعد بين المستويات المكتشفة ضمن نفس النافذة الزمنية."
)


@dataclass(frozen=True)
class SupportResistanceEvidence:
    nearest_support: Optional[float]
    major_support: Optional[float]
    nearest_resistance: Optional[float]
    major_resistance: Optional[float]
    breakout_level: Optional[float]
    breakdown_level: Optional[float]
    evidence_ar: str


def derive_support_resistance(
    price: Optional[float], levels: Optional[SupportResistanceLevels]
) -> SupportResistanceEvidence:
    if price is None or levels is None or (not levels.support and not levels.resistance):
        return SupportResistanceEvidence(None, None, None, None, None, None, "")

    supports_below = sorted((s for s in levels.support if s <= price), reverse=True)
    resistances_above = sorted(r for r in levels.resistance if r >= price)

    nearest_support = supports_below[0] if supports_below else None
    major_support = supports_below[-1] if supports_below else None
    nearest_resistance = resistances_above[0] if resistances_above else None
    major_resistance = resistances_above[-1] if resistances_above else None

    return SupportResistanceEvidence(
        nearest_support=nearest_support,
        major_support=major_support,
        nearest_resistance=nearest_resistance,
        major_resistance=major_resistance,
        # A "breakout" clears the nearest overhead resistance; a
        # "breakdown" clears the nearest support beneath -- the same
        # two levels already surfaced above, just under the labels a
        # trader actually asks "what do I need to see broken?" for.
        breakout_level=nearest_resistance,
        breakdown_level=nearest_support,
        evidence_ar=_SUPPORT_RESISTANCE_EVIDENCE_AR,
    )


_LIQUIDITY_QUALITY_LABELS_AR = {
    "HIGH": "سيولة جيدة",
    "MEDIUM": "سيولة مقبولة",
    "LOW": "سيولة محدودة",
    "UNKNOWN": "غير محددة",
}


def liquidity_quality_label(liquidity_score: Optional[float]) -> str:
    if liquidity_score is None:
        return _LIQUIDITY_QUALITY_LABELS_AR["UNKNOWN"]
    if liquidity_score >= 70.0:
        return _LIQUIDITY_QUALITY_LABELS_AR["HIGH"]
    if liquidity_score >= 40.0:
        return _LIQUIDITY_QUALITY_LABELS_AR["MEDIUM"]
    return _LIQUIDITY_QUALITY_LABELS_AR["LOW"]


@dataclass(frozen=True)
class AccumulationEvidence:
    accumulation_score: Optional[float]
    assessment_ar: str
    volume_confirms_decision: Optional[bool]
    abnormal_volume: bool


def derive_accumulation_evidence(
    obv_volume_score: Optional[float],
    relative_volume: Optional[float],
    direction: int,
) -> AccumulationEvidence:
    """`obv_volume_score` is `scoring.volume_score`'s existing OBV-trend
    score (0-100, 50=neutral) -- reused, not recomputed.
    `relative_volume` (current bar / 20-bar average volume) is real
    when the live quote carries a volume figure; both are optional and
    genuinely absent, never defaulted to a number, when unavailable.

    Deliberately cautious language throughout ("إشارات تجميع محتملة",
    never "تجميع مؤكد") -- OBV direction plus a volume-ratio spike is
    real, but indirect, evidence; it is not the same as confirmed
    institutional order-flow data, which this platform does not have.
    """
    abnormal_volume = relative_volume is not None and relative_volume >= 2.0

    if obv_volume_score is None:
        return AccumulationEvidence(None, "", None, abnormal_volume)

    volume_confirms_decision: Optional[bool] = None
    if direction != 0:
        obv_bullish = obv_volume_score > 50.0
        volume_confirms_decision = obv_bullish if direction > 0 else not obv_bullish

    if obv_volume_score >= 60.0:
        if relative_volume is not None and relative_volume >= 1.5:
            assessment = "إشارات تجميع محتملة مدعومة بحجم تداول أعلى من المعتاد."
        else:
            assessment = "إشارات تجميع محتملة بناءً على اتجاه التدفق النقدي التراكمي (OBV)."
    elif obv_volume_score <= 40.0:
        if relative_volume is not None and relative_volume >= 1.5:
            assessment = "إشارات توزيع محتملة مدعومة بحجم تداول أعلى من المعتاد."
        else:
            assessment = "إشارات توزيع محتملة بناءً على اتجاه التدفق النقدي التراكمي (OBV)."
    else:
        assessment = "لا توجد إشارة تجميع أو توزيع واضحة حاليًا."

    return AccumulationEvidence(
        accumulation_score=obv_volume_score,
        assessment_ar=assessment,
        volume_confirms_decision=volume_confirms_decision,
        abnormal_volume=abnormal_volume,
    )


_TREND_DIRECTION_LABELS_AR = {1: "صاعد", -1: "هابط", 0: "غير واضح"}


def trend_direction_and_strength_labels(trend_score: Optional[float], adx: Optional[float]) -> Tuple[str, str]:
    """Direction from which side of neutral (50) `trend_score` falls
    on; strength from ADX's own conventional bands (already the
    threshold `scoring.trend_score` itself uses to decide whether to
    apply an ADX conviction bonus at all)."""
    if trend_score is None:
        direction_ar = _TREND_DIRECTION_LABELS_AR[0]
    elif trend_score > 55.0:
        direction_ar = _TREND_DIRECTION_LABELS_AR[1]
    elif trend_score < 45.0:
        direction_ar = _TREND_DIRECTION_LABELS_AR[-1]
    else:
        direction_ar = _TREND_DIRECTION_LABELS_AR[0]

    if adx is None:
        strength_ar = "غير محددة"
    elif adx >= 40.0:
        strength_ar = "قوي جدًا"
    elif adx >= 25.0:
        strength_ar = "قوي"
    elif adx >= 15.0:
        strength_ar = "معتدل"
    else:
        strength_ar = "ضعيف"

    return direction_ar, strength_ar


def estimated_days_to_target(
    price: Optional[float], target: Optional[float], atr_value: Optional[float]
) -> Optional[int]:
    """A real, ATR-derived estimate ("at this average daily true
    range, how many bars to cover this distance") -- not a fabricated
    date. `None` whenever price/target/ATR aren't all available, or
    ATR is non-positive (no meaningful velocity to divide by)."""
    if price is None or target is None or atr_value is None or atr_value <= 0:
        return None
    distance = abs(target - price)
    if distance == 0:
        return 0
    return max(1, round(distance / atr_value))


def estimated_days_to_all_targets(
    price: Optional[float], targets: List[Optional[float]], atr_value: Optional[float]
) -> List[Optional[int]]:
    return [estimated_days_to_target(price, t, atr_value) for t in targets]
