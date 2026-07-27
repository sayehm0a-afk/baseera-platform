"""ConfidenceValidator: bands and narrates `InvestmentDecision.
confidence`.

It never recomputes the number -- confidence scoring already lives in
`RecommendationEngine`/`AIDecisionEngine` (see those modules' own
docstrings) -- this module's only job is turning an already-final
number into a plain-language band and an honest explanation of what
drove it up or down, citing which contributor categories were
unavailable and whether the evidence conflicted.
"""

from src.analysis.analyst.types import ConfidenceAssessment, ConflictAssessment, ConfidenceBand, Evidence

_VERY_HIGH_THRESHOLD = 85.0
_HIGH_THRESHOLD = 65.0
_MODERATE_THRESHOLD = 45.0
_LOW_THRESHOLD = 25.0


def _band(confidence: float) -> ConfidenceBand:
    if confidence >= _VERY_HIGH_THRESHOLD:
        return ConfidenceBand.VERY_HIGH
    if confidence >= _HIGH_THRESHOLD:
        return ConfidenceBand.HIGH
    if confidence >= _MODERATE_THRESHOLD:
        return ConfidenceBand.MODERATE
    if confidence >= _LOW_THRESHOLD:
        return ConfidenceBand.LOW
    return ConfidenceBand.VERY_LOW


class ConfidenceValidator:
    def validate(self, evidence: Evidence, conflict: ConflictAssessment) -> ConfidenceAssessment:
        confidence = evidence.decision.confidence
        band = _band(confidence)
        narrative = _build_narrative(evidence, conflict, band)
        return ConfidenceAssessment(confidence=confidence, band=band, narrative=narrative)


def _build_narrative(evidence: Evidence, conflict: ConflictAssessment, band: ConfidenceBand) -> str:
    unavailable = sorted(b.category for b in evidence.contributor_breakdown if not b.available)
    parts = [f"Confidence in this recommendation is {evidence.decision.confidence:.1f}% ({band.value.replace('_', ' ').lower()})."]

    if unavailable:
        parts.append(f"This is reduced by missing data from: {', '.join(unavailable)}.")
    else:
        parts.append("Every analysis category had data available for this run.")

    if conflict.has_conflict:
        parts.append("Confidence is further tempered by disagreement between categories, described above.")
    else:
        parts.append("No significant disagreement between categories was found.")

    return " ".join(parts)
