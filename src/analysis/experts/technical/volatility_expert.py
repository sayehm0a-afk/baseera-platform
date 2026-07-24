"""Volatility Expert: Technical Council's third BEIF expert (M2.9),
following the same architectural shape Trend Expert (M2.7) and
Momentum Expert (M2.8) established -- with one deliberate, documented
deviation from both: Volatility Expert is **non-directional by
design**.

Reads only the already-computed bollinger/atr_14 indicator outputs
from a supplied "technical_analysis" engine result envelope -- never a
raw OHLCV DataFrame, never recomputes Bollinger Bands or ATR itself
(BEIF Section 14's anti-duplication rule, enforced structurally by
this function's own signature, exactly as Trend/Momentum Expert's
signatures already are).

======================================================================
ARCHITECTURAL DECISION 1: non-directional output (Document 1 Section
5.3, BEIF Section 5)
======================================================================
Volatility measures the *magnitude* of price dispersion, not its
*direction* -- a stock can be highly volatile while going up, going
down, or going nowhere. Forcing a BULLISH/BEARISH read out of a
volatility measure would be a category error, not merely a design
choice: it would fabricate directional evidence this expert has no
basis to produce (BIIC Article X). `direction` is therefore always
`ExpertDirection.NEUTRAL`, and `normalized_score` is deliberately
repurposed from a signed [-1, 1] direction-and-strength value into an
unsigned [0, 1] *volatility-intensity* value (0 = maximally
compressed, 1 = maximally expanded) -- a disclosed reuse of the same
field, not a new one, exactly as Document 1 Section 5.3 specifies.
Because there is no direction to disagree about, this expert's
`conflicts` tuple is always empty by construction -- there is no
"agreement vs. disagreement" concept for a single, non-directional
quantity the way there is between two directional evidence sources.

======================================================================
ARCHITECTURAL DECISION 2: two independent, dimensionless volatility
measures, never one indicator's raw (price-scale-dependent) value
======================================================================
`atr_14` is reported in absolute price units -- an ATR of 2.0 means
something completely different for a SAR 10 stock than a SAR 200
stock, and using it directly as intensity evidence would silently mix
volatility magnitude with price level, a fabricated and misleading
signal. This expert instead computes two independent, dimensionless
("relative to price level") measures:

  - **Bollinger relative bandwidth**: `(upper - lower) / middle`.
    This is John Bollinger's own standard "%B width" formulation, not
    an invented ratio -- a well-established, price-scale-independent
    measure of how wide the bands currently are.
  - **ATR relative to price**: `atr_14 / middle`, using the Bollinger
    middle band (a 20-period SMA of close) as the price-level
    reference, since no separate raw close price is available in this
    expert's input (per BEIF Section 14, it must not read one). This
    is the same "normalized ATR" / "ATR percentage" convention widely
    used in technical analysis practice, not a fabricated formula.

Both measures independently answer the same underlying question ("how
large is price dispersion relative to price level right now") via
genuinely different methodologies -- Bollinger from a rolling standard
deviation of closes, ATR from true range -- so agreement between them
is real corroboration, not double-counting of the same computation
(BEIF Section 6/16's double-counting guard is about two experts, or
two rules, re-deriving the *same* fact; these are two independently
computed facts about the same underlying concept).

======================================================================
ARCHITECTURAL DECISION 3: no fabricated compressed/expanded threshold
======================================================================
Unlike ADX (Trend Expert), Bollinger bandwidth and ATR-relative-to-
price have no universally standard, pre-calibrated scale the way ADX's
own documented 0-100 range does. This expert therefore does **not**
assert a specific numeric threshold for "compressed" vs. "expanded"
volatility (e.g. it never claims "bandwidth above 0.10 means
expanded") -- doing so without empirical, regime-calibrated support
would be exactly the invented-confidence BIIC Article X forbids and
Document 1 Section 10/Document 7's whole discipline exists to prevent.
`normalized_score` is the raw, dimensionless relative measure itself
(clamped to [0, 1] purely as a numeric safety bound against a
pathological input, never as an asserted "this counts as expanded"
line) -- a categorical compressed/normal/expanded read is left to a
future Learning Engine (Document 7) once real, accumulated outcome
data exists to calibrate one, and this expert's `limitations` field
discloses that gap explicitly on every result.

Confidence is capped below 1.0 unconditionally (Document 1 Section 13,
BIIC Article IV.4), identical to Trend/Momentum Expert.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertSpec
from src.analysis.experts.types import Council, EvidenceItem, ExpertDirection, ExpertResult, ExpertStatus

EXPERT_ID = "technical.volatility"
_REQUIRED_METRICS: Tuple[str, ...] = ("bollinger", "atr_14")
_CONFIDENCE_CEILING = 0.9


def _empty_result(symbol: str, as_of: datetime, freshness: Freshness, reason: str) -> ExpertResult:
    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Volatility Expert",
        council=Council.TECHNICAL,
        domain="volatility",
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


def _extract_bollinger_middle(bollinger_latest: object, warnings: List[str]) -> Optional[float]:
    """Returns the middle band, or None if bollinger_latest is
    malformed/unusable as a price-level reference -- never raises."""
    if not isinstance(bollinger_latest, dict):
        warnings.append("'bollinger' latest value is not the expected {upper, middle, lower} shape")
        return None
    middle = bollinger_latest.get("middle")
    if middle is None:
        warnings.append("'bollinger' latest value has no defined middle band")
        return None
    middle = float(middle)
    if middle == 0.0:
        warnings.append("'bollinger' middle band is zero; cannot use it as a price-level reference")
        return None
    return middle


def compute_volatility_expert(symbol: str, envelopes: Dict[str, EngineResultEnvelope]) -> ExpertResult:
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
    used_metrics: set = set()
    contributions: List[float] = []

    middle: Optional[float] = None
    if "bollinger" in raw_values:
        middle = _extract_bollinger_middle(raw_values["bollinger"], warnings)

    if "bollinger" in raw_values and middle is not None:
        bollinger_latest = raw_values["bollinger"]
        upper = bollinger_latest.get("upper")
        lower = bollinger_latest.get("lower")
        if upper is None or lower is None:
            warnings.append("'bollinger' latest value is missing an upper or lower band")
        else:
            upper = float(upper)
            lower = float(lower)
            if upper < lower:
                warnings.append(
                    "'bollinger' upper band is below the lower band (malformed/degenerate input); "
                    "relative bandwidth not computed"
                )
            else:
                relative_bandwidth = (upper - lower) / abs(middle)
                relative_bandwidth = max(0.0, min(1.0, relative_bandwidth))
                rule_id = "volatility.bollinger_relative_bandwidth"
                evidence.append(
                    EvidenceItem(
                        metric_name="bollinger",
                        observed_value={"upper": upper, "middle": middle, "lower": lower},
                        rule_id=rule_id,
                        contribution=relative_bandwidth,
                    )
                )
                rule_ids.append(rule_id)
                used_metrics.add("bollinger")
                contributions.append(relative_bandwidth)

    if "atr_14" in raw_values:
        if middle is None:
            warnings.append(
                "'atr_14' is present but could not be normalized without a usable Bollinger "
                "middle band as a price-level reference"
            )
        else:
            atr = float(raw_values["atr_14"])
            relative_atr = max(0.0, min(1.0, atr / abs(middle)))
            rule_id = "volatility.atr_relative_to_price"
            evidence.append(
                EvidenceItem(
                    metric_name="atr_14",
                    observed_value={"atr_14": atr, "reference_price": middle},
                    rule_id=rule_id,
                    contribution=relative_atr,
                )
            )
            rule_ids.append(rule_id)
            used_metrics.add("atr_14")
            contributions.append(relative_atr)

    normalized_score: Optional[float]
    if contributions:
        normalized_score = max(0.0, min(1.0, sum(contributions) / len(contributions)))
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
        confidence = 0.0
    else:
        completeness_factor = available_count / required_count
        # No conflict concept exists for this non-directional expert (see
        # module docstring, Architectural Decision 1) -- "agreement" here
        # means both independent measures corroborated each other, not
        # that they pointed the same direction.
        corroboration_factor = 1.0 if len(contributions) == 2 else 0.7
        confidence = max(0.0, min(_CONFIDENCE_CEILING, completeness_factor * corroboration_factor))

    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Volatility Expert",
        council=Council.TECHNICAL,
        domain="volatility",
        symbol=symbol,
        as_of=envelope.as_of,
        direction=ExpertDirection.NEUTRAL,
        normalized_score=normalized_score,
        confidence=confidence,
        completeness=completeness,
        freshness=envelope.freshness,
        evidence=tuple(evidence),
        contributing_metrics=_REQUIRED_METRICS,
        rule_ids=tuple(rule_ids),
        warnings=tuple(warnings),
        conflicts=(),
        limitations=(
            "non-directional by design -- direction is always NEUTRAL and must never be read "
            "as a bullish/bearish signal (Document 1 Section 5.3)",
            "normalized_score is a raw, dimensionless relative-volatility measure, not a "
            "calibrated compressed/normal/expanded classification -- no empirically-supported "
            "threshold for that classification exists yet (Document 1 Section 10, Document 7)",
            "reads only bollinger/atr_14; does not itself assess risk -- risk interpretation "
            "of elevated volatility is a future Risk Council expert's exclusive job "
            "(Document 3 Section 5.1, BEIF Section 14)",
        ),
        version="1.0.0",
        metadata={},
    )


DEFAULT_EXPERT_REGISTRY.register(
    ExpertSpec(
        expert_id=EXPERT_ID,
        name="Volatility Expert",
        council=Council.TECHNICAL,
        domain="volatility",
        version="1.0.0",
        status=ExpertStatus.EXPERIMENTAL,
        required_engines=["technical_analysis"],
        contributing_metrics=list(_REQUIRED_METRICS),
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=compute_volatility_expert,
    )
)
