"""ConflictResolver: detects when the evidence does not unanimously
agree -- e.g. strong technical momentum against weak fundamentals --
and narrates it honestly instead of letting a single blended score
paper over the disagreement.

`tension_level` is deliberately anchored to the Technical-vs-
Fundamental spread specifically: those are the two largest, most
independent legs of every decision (see `AIDecisionEngine.
default_contributors()`), so their disagreement is the single most
informative conflict signal available, even though `conflicting_
categories` reports every opposing pair for completeness.
"""

import itertools
from typing import List, Optional, Tuple

from src.analysis.analyst.types import ConflictAssessment, Evidence, InterpretedSignals, TensionLevel

_TECHNICAL_CATEGORY = "Technical Analysis"
_FUNDAMENTAL_CATEGORY = "Fundamental Analysis"

_HIGH_TENSION_THRESHOLD = 30.0
_MODERATE_TENSION_THRESHOLD = 15.0
_MILD_TENSION_THRESHOLD = 5.0


def _category_points(evidence: Evidence, category: str) -> Optional[float]:
    for breakdown in evidence.contributor_breakdown:
        if breakdown.category == category and breakdown.available:
            return breakdown.points
    return None


def _find_conflicting_pairs(category_tilts: dict) -> List[Tuple[str, str]]:
    directional = {c: t for c, t in category_tilts.items() if t in ("bullish", "bearish")}
    pairs = []
    for (category_a, tilt_a), (category_b, tilt_b) in itertools.combinations(directional.items(), 2):
        if tilt_a != tilt_b:
            pairs.append((category_a, category_b))
    return pairs


def _tension_level(technical_points: Optional[float], fundamental_points: Optional[float]) -> TensionLevel:
    if technical_points is None or fundamental_points is None:
        return TensionLevel.NONE
    spread = abs(technical_points - fundamental_points)
    if spread >= _HIGH_TENSION_THRESHOLD:
        return TensionLevel.HIGH
    if spread >= _MODERATE_TENSION_THRESHOLD:
        return TensionLevel.MODERATE
    if spread >= _MILD_TENSION_THRESHOLD:
        return TensionLevel.MILD
    return TensionLevel.NONE


class ConflictResolver:
    def resolve(self, evidence: Evidence, interpreted: InterpretedSignals) -> ConflictAssessment:
        conflicting_pairs = _find_conflicting_pairs(interpreted.category_tilts)
        technical_points = _category_points(evidence, _TECHNICAL_CATEGORY)
        fundamental_points = _category_points(evidence, _FUNDAMENTAL_CATEGORY)
        tension_level = _tension_level(technical_points, fundamental_points)

        has_conflict = bool(conflicting_pairs) or tension_level is not TensionLevel.NONE
        narrative = _build_narrative(conflicting_pairs, tension_level, technical_points, fundamental_points)
        alternative_scenarios = _build_alternative_scenarios(evidence, interpreted, has_conflict)

        return ConflictAssessment(
            has_conflict=has_conflict,
            tension_level=tension_level,
            conflicting_categories=conflicting_pairs,
            narrative=narrative,
            alternative_scenarios=alternative_scenarios,
        )


def _build_narrative(
    conflicting_pairs: List[Tuple[str, str]],
    tension_level: TensionLevel,
    technical_points: Optional[float],
    fundamental_points: Optional[float],
) -> str:
    if not conflicting_pairs and tension_level is TensionLevel.NONE:
        return "The available evidence is broadly aligned, with no significant disagreement between categories."

    parts = []
    if technical_points is not None and fundamental_points is not None and tension_level is not TensionLevel.NONE:
        parts.append(
            f"Technical Analysis ({technical_points:+.1f}) and Fundamental Analysis ({fundamental_points:+.1f}) "
            f"show {tension_level.value.lower()} disagreement."
        )
    other_pairs = [pair for pair in conflicting_pairs if set(pair) != {_TECHNICAL_CATEGORY, _FUNDAMENTAL_CATEGORY}]
    if other_pairs:
        pair_text = "; ".join(f"{a} vs {b}" for a, b in other_pairs)
        parts.append(f"Additional opposing categories: {pair_text}.")
    return " ".join(parts) if parts else "The available evidence shows some disagreement between categories."


def _build_alternative_scenarios(evidence: Evidence, interpreted: InterpretedSignals, has_conflict: bool) -> List[str]:
    scenarios = []
    if evidence.decision.confidence < 50.0 or has_conflict:
        top_bearish = interpreted.bearish_factors[0] if interpreted.bearish_factors else None
        top_bullish = interpreted.bullish_factors[0] if interpreted.bullish_factors else None
        if top_bearish is not None:
            scenarios.append(
                f"If the bearish factor from {top_bearish.category.lower()} resolves or reverses, the case for this "
                "recommendation would strengthen."
            )
        if top_bullish is not None:
            scenarios.append(
                f"If the bullish factor from {top_bullish.category.lower()} weakens or reverses, the case for this "
                "recommendation would weaken."
            )
    if not scenarios:
        scenarios.append(
            "No material alternative scenario was identified; the current mix of evidence would need a "
            "significant new development to change this recommendation."
        )
    return scenarios
