"""Trend Expert: Basirah's first BEIF expert (M2.7), and the reference
implementation the rest of Technical Council's v1 buildout (Momentum,
Volatility, Volume, Candlestick/Price Action -- BEIF Section 3.A) will
follow the same shape as.

Reads only the already-computed sma_20/ema_20/adx_14/supertrend
indicator outputs from a supplied "technical_analysis" engine result
envelope -- never a raw OHLCV DataFrame, never recomputes a moving
average or ADX itself (BEIF Section 14's anti-duplication rule,
enforced structurally here by this function's own signature: it has
no parameter through which it could receive raw price data).

Doctrine (Basirah Technical Analysis Master Framework, Section 2):
  - EMA-20 above SMA-20 is read as a bullish tilt (a faster average
    running above a slower one); below, bearish.
  - SuperTrend's own direction flag is read directly.
  - ADX-14 is non-directional -- it scales the *magnitude* of whatever
    direction the other two evidence sources agree on, never
    originates a direction itself, and its 0-100 range is used as
    ADX's own well-established, standard scale, not an invented
    calibration.
  - Disagreement between the two directional sources is disclosed as
    a conflict and punished harder than agreement is rewarded
    (BIIC Article III.3), never silently averaged away without trace.

Confidence is capped below 1.0 unconditionally (Document 1 Section 13,
BIIC Article IV.4) -- Trend Expert never claims full certainty, no
matter how strong or well-agreed its available evidence is.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertSpec
from src.analysis.experts.types import Council, EvidenceItem, ExpertDirection, ExpertResult, ExpertStatus

EXPERT_ID = "technical.trend"
_REQUIRED_METRICS: Tuple[str, ...] = ("sma_20", "ema_20", "adx_14", "supertrend")
_CONFIDENCE_CEILING = 0.9
_DIRECTION_EPSILON = 0.05
_ADX_SCALE = 50.0  # ADX's own standard 0-100 range; 50+ already reads as a very strong trend


def _collect_available_metrics(technical_result: object, warnings: List[str]) -> Dict[str, object]:
    values: Dict[str, object] = {}
    for metric in _REQUIRED_METRICS:
        try:
            output = technical_result.get(metric)  # type: ignore[attr-defined]
        except KeyError:
            warnings.append(f"required metric '{metric}' missing from technical_analysis result")
            continue
        latest = output.latest()
        if latest is None:
            warnings.append(f"required metric '{metric}' had no defined latest value")
            continue
        values[metric] = latest
    return values


def _empty_result(symbol: str, as_of: datetime, freshness: Freshness, reason: str) -> ExpertResult:
    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Trend Expert",
        council=Council.TECHNICAL,
        domain="trend",
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


def compute_trend_expert(symbol: str, envelopes: Dict[str, EngineResultEnvelope]) -> ExpertResult:
    envelope = envelopes.get("technical_analysis")
    if envelope is None:
        return _empty_result(
            symbol,
            as_of=datetime.now(timezone.utc),
            freshness=Freshness.UNKNOWN,
            reason="required engine result envelope 'technical_analysis' was not supplied",
        )

    warnings: List[str] = []
    values = _collect_available_metrics(envelope.result, warnings)

    evidence: List[EvidenceItem] = []
    rule_ids: List[str] = []
    direction_signs: List[int] = []
    # Metrics that actually contributed usable evidence to a rule -- distinct
    # from `values` (raw, present-but-not-necessarily-usable latest() output).
    # A present-but-malformed value (e.g. supertrend's latest() not being a
    # dict) must not count toward completeness just because it was present.
    used_metrics: set = set()

    if "sma_20" in values and "ema_20" in values:
        sma = float(values["sma_20"])
        ema = float(values["ema_20"])
        sign = 1 if ema > sma else (-1 if ema < sma else 0)
        rule_id = "trend.ema_above_sma_is_bullish"
        evidence.append(
            EvidenceItem(
                metric_name="ema_20_vs_sma_20",
                observed_value={"ema_20": ema, "sma_20": sma},
                rule_id=rule_id,
                contribution=float(sign),
            )
        )
        rule_ids.append(rule_id)
        direction_signs.append(sign)
        used_metrics.update({"sma_20", "ema_20"})

    if "supertrend" in values:
        supertrend_latest = values["supertrend"]
        direction_value = supertrend_latest.get("direction") if isinstance(supertrend_latest, dict) else None
        if direction_value is not None:
            sign = 1 if direction_value > 0 else (-1 if direction_value < 0 else 0)
            rule_id = "trend.supertrend_direction"
            evidence.append(
                EvidenceItem(
                    metric_name="supertrend",
                    observed_value=direction_value,
                    rule_id=rule_id,
                    contribution=float(sign),
                )
            )
            rule_ids.append(rule_id)
            direction_signs.append(sign)
            used_metrics.add("supertrend")
        else:
            warnings.append("'supertrend' latest value had no defined direction")

    conflicts: List[str] = []
    if len(direction_signs) >= 2:
        nonzero_signs = {sign for sign in direction_signs if sign != 0}
        if len(nonzero_signs) > 1:
            conflicts.append(
                "ema_20-vs-sma_20 relationship and supertrend direction disagree on trend direction"
            )

    strength: Optional[float] = None
    if "adx_14" in values:
        adx = float(values["adx_14"])
        strength = max(0.0, min(1.0, adx / _ADX_SCALE))
        rule_id = "trend.adx_strength_scaling"
        evidence.append(
            EvidenceItem(metric_name="adx_14", observed_value=adx, rule_id=rule_id, contribution=strength)
        )
        rule_ids.append(rule_id)
        used_metrics.add("adx_14")

    normalized_score: Optional[float]
    if direction_signs:
        average_sign = sum(direction_signs) / len(direction_signs)
        effective_strength = strength if strength is not None else 0.5
        normalized_score = max(-1.0, min(1.0, average_sign * effective_strength))
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

    if not direction_signs:
        direction = ExpertDirection.NEUTRAL
    elif conflicts:
        direction = ExpertDirection.MIXED
    elif normalized_score is not None and normalized_score > _DIRECTION_EPSILON:
        direction = ExpertDirection.BULLISH
    elif normalized_score is not None and normalized_score < -_DIRECTION_EPSILON:
        direction = ExpertDirection.BEARISH
    else:
        direction = ExpertDirection.NEUTRAL

    if not direction_signs:
        confidence = 0.0
    else:
        completeness_factor = available_count / required_count
        if conflicts:
            # Disagreement is punished harder than agreement is rewarded (BIIC Article III.3).
            agreement_factor = 0.4
        elif len(direction_signs) < 2:
            # Only one directional source available -- agreement can't be confirmed either way.
            agreement_factor = 0.7
        else:
            agreement_factor = 1.0
        confidence = max(0.0, min(_CONFIDENCE_CEILING, completeness_factor * agreement_factor))

    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Trend Expert",
        council=Council.TECHNICAL,
        domain="trend",
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
            "reads only sma_20/ema_20/adx_14/supertrend; does not yet incorporate Market "
            "Structure evidence (BOS/CHoCH/order blocks/liquidity zones), deferred pending "
            "a swing-high/low and gap-detection indicator not yet in IndicatorRegistry "
            "(Basirah Technical Analysis Master Framework, Section 3.4)",
        ),
        version="1.0.0",
        metadata={},
    )


DEFAULT_EXPERT_REGISTRY.register(
    ExpertSpec(
        expert_id=EXPERT_ID,
        name="Trend Expert",
        council=Council.TECHNICAL,
        domain="trend",
        version="1.0.0",
        status=ExpertStatus.EXPERIMENTAL,
        required_engines=["technical_analysis"],
        contributing_metrics=list(_REQUIRED_METRICS),
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=compute_trend_expert,
    )
)
