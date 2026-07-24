"""Momentum Expert: Technical Council's second BEIF expert (M2.8),
following the exact shape Trend Expert (M2.7) established.

Reads only the already-computed rsi_14/macd indicator outputs from a
supplied "technical_analysis" engine result envelope -- never a raw
OHLCV DataFrame, never recomputes RSI or MACD itself (BEIF Section 14's
anti-duplication rule, enforced structurally by this function's own
signature, exactly as Trend Expert's is).

Doctrine (Basirah Technical Analysis Master Framework, Section 5):
  - RSI-14 is read as a continuous, symmetric momentum-direction-and-
    magnitude measure -- (rsi - 50) / 50, clamped to [-1, 1] -- never
    as a binary "overbought means sell" reversal trigger. This is a
    deliberate design choice: Document 1 Section 5.2 identifies exactly
    that misapplication ("RSI can remain overbought or oversold for
    extended periods during a strong trend without reversing") as
    RSI's most common failure mode in retail practice, and this expert
    avoids it by construction rather than by convention alone. An RSI
    reading past the conventional 70/30 overbought/oversold bounds is
    still disclosed via `warnings` -- informational context, never a
    reversal call this expert did not earn the right to make.
  - MACD's histogram sign (macd_line above/below signal_line) is read
    as a directional confirmation, at full weight (+1/-1), never scaled
    by histogram magnitude -- MACD's absolute value is price-scale-
    dependent with no universal, non-fabricated normalization available
    the way ADX's own standard 0-100 range gave Trend Expert a
    principled magnitude scale. Inventing one here would be exactly the
    kind of uncalibrated precision BIIC Article X forbids.
  - Disagreement between RSI's momentum reading and MACD's histogram
    sign is disclosed as a conflict and punished harder than agreement
    is rewarded (BIIC Article III.3), identical to Trend Expert.

Confidence is capped below 1.0 unconditionally (Document 1 Section 13,
BIIC Article IV.4), identical to Trend Expert.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertSpec
from src.analysis.experts.types import Council, EvidenceItem, ExpertDirection, ExpertResult, ExpertStatus

EXPERT_ID = "technical.momentum"
_REQUIRED_METRICS: Tuple[str, ...] = ("rsi_14", "macd")
_CONFIDENCE_CEILING = 0.9
_DIRECTION_EPSILON = 0.05
_RSI_MIDPOINT = 50.0
_RSI_SCALE = 50.0
_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD = 30.0


def _empty_result(symbol: str, as_of: datetime, freshness: Freshness, reason: str) -> ExpertResult:
    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Momentum Expert",
        council=Council.TECHNICAL,
        domain="momentum",
        symbol=symbol,
        as_of=as_of,
        direction=ExpertDirection.NEUTRAL,
        normalized_score=None,
        confidence=0.0,
        completeness=DataCompleteness.INSUFFICIENT,
        freshness=freshness,
        evidence=(),
        contributing_metrics=_REQUIRED_METRICS,
        rule_ids=(),
        warnings=(reason,),
        conflicts=(),
        limitations=(),
        version="1.0.0",
        metadata={},
    )


def compute_momentum_expert(symbol: str, envelopes: Dict[str, EngineResultEnvelope]) -> ExpertResult:
    envelope = envelopes.get("technical_analysis")
    if envelope is None:
        return _empty_result(
            symbol,
            as_of=datetime.now(timezone.utc),
            freshness=Freshness.UNKNOWN,
            reason="required engine result envelope 'technical_analysis' was not supplied",
        )

    warnings: List[str] = []
    technical_result = envelope.result

    raw_values: Dict[str, object] = {}
    for metric in _REQUIRED_METRICS:
        try:
            output = technical_result.get(metric)
        except KeyError:
            warnings.append(f"required metric '{metric}' missing from technical_analysis result")
            continue
        latest = output.latest()
        if latest is None:
            warnings.append(f"required metric '{metric}' had no defined latest value")
            continue
        raw_values[metric] = latest

    evidence: List[EvidenceItem] = []
    rule_ids: List[str] = []
    direction_signs: List[int] = []
    used_metrics: set = set()

    rsi_contribution: Optional[float] = None
    if "rsi_14" in raw_values:
        rsi = float(raw_values["rsi_14"])
        rsi_contribution = max(-1.0, min(1.0, (rsi - _RSI_MIDPOINT) / _RSI_SCALE))
        rule_id = "momentum.rsi_scaled_from_midpoint"
        evidence.append(
            EvidenceItem(metric_name="rsi_14", observed_value=rsi, rule_id=rule_id, contribution=rsi_contribution)
        )
        rule_ids.append(rule_id)
        used_metrics.add("rsi_14")
        sign = 1 if rsi_contribution > 0 else (-1 if rsi_contribution < 0 else 0)
        direction_signs.append(sign)

        if rsi >= _RSI_OVERBOUGHT:
            warnings.append(
                f"rsi_14={rsi:.2f} is at or above the conventional overbought threshold "
                f"({_RSI_OVERBOUGHT:.0f}); read as strong bullish momentum, not an automatic "
                "reversal signal (Document 1 Section 5.2)"
            )
        elif rsi <= _RSI_OVERSOLD:
            warnings.append(
                f"rsi_14={rsi:.2f} is at or below the conventional oversold threshold "
                f"({_RSI_OVERSOLD:.0f}); read as strong bearish momentum, not an automatic "
                "reversal signal (Document 1 Section 5.2)"
            )

    macd_contribution: Optional[float] = None
    if "macd" in raw_values:
        macd_latest = raw_values["macd"]
        histogram = macd_latest.get("histogram") if isinstance(macd_latest, dict) else None
        if histogram is not None:
            sign = 1 if histogram > 0 else (-1 if histogram < 0 else 0)
            macd_contribution = float(sign)
            rule_id = "momentum.macd_histogram_sign"
            evidence.append(
                EvidenceItem(
                    metric_name="macd", observed_value=histogram, rule_id=rule_id, contribution=macd_contribution
                )
            )
            rule_ids.append(rule_id)
            used_metrics.add("macd")
            direction_signs.append(sign)
        else:
            warnings.append("'macd' latest value had no defined histogram")

    conflicts: List[str] = []
    if len(direction_signs) >= 2:
        nonzero_signs = {sign for sign in direction_signs if sign != 0}
        if len(nonzero_signs) > 1:
            conflicts.append("rsi_14 momentum reading and macd histogram sign disagree on momentum direction")

    normalized_score: Optional[float]
    contributions = [value for value in (rsi_contribution, macd_contribution) if value is not None]
    if contributions:
        normalized_score = max(-1.0, min(1.0, sum(contributions) / len(contributions)))
    else:
        normalized_score = None

    required_count = len(_REQUIRED_METRICS)
    available_count = len(used_metrics)
    if available_count == 0:
        completeness = DataCompleteness.INSUFFICIENT
    elif available_count == required_count:
        completeness = DataCompleteness.COMPLETE
    else:
        completeness = DataCompleteness.PARTIAL

    if not contributions:
        direction = ExpertDirection.NEUTRAL
    elif conflicts:
        direction = ExpertDirection.MIXED
    elif normalized_score is not None and normalized_score > _DIRECTION_EPSILON:
        direction = ExpertDirection.BULLISH
    elif normalized_score is not None and normalized_score < -_DIRECTION_EPSILON:
        direction = ExpertDirection.BEARISH
    else:
        direction = ExpertDirection.NEUTRAL

    if not contributions:
        confidence = 0.0
    else:
        completeness_factor = available_count / required_count
        if conflicts:
            # Disagreement is punished harder than agreement is rewarded (BIIC Article III.3).
            agreement_factor = 0.4
        elif len(contributions) < 2:
            # Only one directional source available -- agreement can't be confirmed either way.
            agreement_factor = 0.7
        else:
            agreement_factor = 1.0
        confidence = max(0.0, min(_CONFIDENCE_CEILING, completeness_factor * agreement_factor))

    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Momentum Expert",
        council=Council.TECHNICAL,
        domain="momentum",
        symbol=symbol,
        as_of=envelope.as_of,
        direction=direction,
        normalized_score=normalized_score,
        confidence=confidence,
        completeness=completeness,
        freshness=envelope.freshness,
        evidence=tuple(evidence),
        contributing_metrics=_REQUIRED_METRICS,
        rule_ids=tuple(rule_ids),
        warnings=tuple(warnings),
        conflicts=tuple(conflicts),
        limitations=(
            "reads only rsi_14/macd; does not read adx_14 or trend context, so an extended "
            "overbought/oversold reading during a strong trend is disclosed via warnings but "
            "not cross-checked against Trend Expert's own evidence -- that cross-check is a "
            "future Signal Engine's job, not this expert's (BEIF Section 3.A rejects a "
            "standalone Signal Confirmation Expert for exactly this reason)",
            "macd histogram is read by sign only, never by magnitude -- no non-fabricated, "
            "price-scale-independent normalization is available for MACD's absolute value "
            "(Document 1 Section 5.1)",
        ),
        version="1.0.0",
        metadata={},
    )


DEFAULT_EXPERT_REGISTRY.register(
    ExpertSpec(
        expert_id=EXPERT_ID,
        name="Momentum Expert",
        council=Council.TECHNICAL,
        domain="momentum",
        version="1.0.0",
        status=ExpertStatus.EXPERIMENTAL,
        required_engines=["technical_analysis"],
        contributing_metrics=list(_REQUIRED_METRICS),
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=compute_momentum_expert,
    )
)
