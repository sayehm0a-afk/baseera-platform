"""Candlestick & Price Action Expert: Technical Council's fifth and
final v1 BEIF expert (M2.11), closing out the v1 set BEIF Section 3.A
defines (Trend, Momentum, Volatility, Volume, Candlestick/Price Action).
Market Structure Expert remains explicitly deferred to v2, exactly as
BEIF already specifies -- this milestone does not amend that boundary.

Reads only the already-computed `candlestick_patterns` indicator output
from a supplied "technical_analysis" engine result envelope -- never a
raw OHLCV DataFrame, never re-detects a pattern itself (BEIF Section
14's anti-duplication rule, enforced structurally here the same way
every prior expert enforces it: this function's signature has no
parameter through which it could receive raw OHLCV bars).

======================================================================
ARCHITECTURAL DECISION 1: reading the indicator's full `.value` (the
list of PatternMatch objects), not `.latest()` -- a different reason
than Volume Expert's (M2.10)
======================================================================
`candlestick_patterns` is registered in `IndicatorRegistry` as
`List[PatternMatch]` (`src/analysis/price_action/candlestick_patterns.py`),
where each `PatternMatch` carries `pattern_name`, `timestamp`, and
`bullish`. `IndicatorOutput.latest()` (src/analysis/types.py) already
collapses this into just the pattern *names* matched at the most recent
matched timestamp -- it discards each match's `bullish` flag entirely.
This expert needs that flag to determine direction, so it reads
`.value` directly and performs its own grouping-by-latest-timestamp,
mirroring exactly what `.latest()` already does internally
(`latest_timestamp = max(match.timestamp for match in matches)`) but
without losing the per-match detail `.latest()` throws away. This is
still only reading an already-computed indicator's own output in full,
never recomputing anything from raw bars -- the same boundary Volume
Expert's own Architectural Decision 1 already established, applied here
for a data-richness reason rather than Volume's history-window reason.

======================================================================
ARCHITECTURAL DECISION 2: per-pattern direction, and why Doji is
deliberately excluded from directional evidence despite carrying a
`bullish` flag in the raw data
======================================================================
Four of the five detected patterns have a fixed, unconditional
directional meaning by construction in `candlestick_patterns.py` itself:
Hammer is always `bullish=True`, Shooting Star always `bullish=False`,
Bullish Engulfing always `bullish=True`, Bearish Engulfing always
`bullish=False`. This expert reads that flag directly as its sign
(`+1`/`-1`) rather than re-deriving it -- re-deriving it would mean
re-inspecting bar geometry the expert has no access to, and re-stating a
value the indicator has already computed would violate the same
anti-duplication principle in spirit even if not in raw-data access.

Doji is different: `detect_patterns` sets its `bullish` flag from
`close >= open`, i.e. which side of an essentially-zero body the close
landed on -- not a real directional signal. A Doji's textbook meaning is
indecision, not direction. Treating a Doji's `bullish` flag as
directional evidence would fabricate a signal the pattern itself does
not carry. This expert therefore still reports every detected Doji as
an `EvidenceItem` (so its detection is visible and auditable) but always
with `contribution=0.0`, and Doji is excluded from the direction-sign
list combined into `normalized_score`/`conflicts` below.

======================================================================
ARCHITECTURAL DECISION 3: no magnitude/strength scale -- unlike Trend's
ADX or Volume's relative-volume ratio
======================================================================
`PatternMatch` carries no numeric field describing how pronounced a
detected pattern is (e.g. wick-to-body ratio) -- `candlestick_patterns.py`
only reports a boolean match per pattern type per bar. There is
therefore no already-computed magnitude to read (reading one would mean
recomputing bar geometry from raw OHLCV, which this expert does not have
access to). `normalized_score` is accordingly the plain average of each
contributing pattern's `+1`/`-1` sign -- already bounded to `[-1, 1]` by
construction -- with no separate strength multiplier, unlike Trend
Expert's ADX-based scaling or Volume Expert's relative-volume transform.
This is a disclosed absence, not an oversight: no non-fabricated
magnitude signal exists at the pattern-detection layer today.

======================================================================
ARCHITECTURAL DECISION 4: the "latest" matched bar may not be the true
latest bar in the underlying series -- a known, disclosed limitation of
the indicator itself, not of this expert
======================================================================
`detect_patterns` only records a `PatternMatch` for bars where a pattern
actually matched. If the most recent bar(s) in the underlying OHLCV
series matched no pattern at all, the `latest_timestamp` this expert (and
`IndicatorOutput.latest()`) computes is the most recent bar that *did*
match something, which can be strictly older than the true last bar.
Neither this expert nor the indicator has access to the true last bar's
timestamp to detect or correct for that gap -- `EngineResultEnvelope.as_of`
is deliberately *not* used as a substitute for that purpose: it records
when the engine last ran (wall-clock time), not the timestamp of the
underlying data's last bar, and the two can differ by an arbitrary
amount (e.g. analysis run today over data current as of last week).
Using it to estimate pattern staleness would conflate two unrelated
kinds of "recency" and could mislead more than it clarifies. This
limitation is disclosed in every result's `limitations` instead.

Confidence is capped below 1.0 unconditionally (Document 1 Section 13,
BIIC Article IV.4), identical to every prior Technical Council expert.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertSpec
from src.analysis.experts.types import Council, EvidenceItem, ExpertDirection, ExpertResult, ExpertStatus

EXPERT_ID = "technical.candlestick"
_REQUIRED_METRICS: Tuple[str, ...] = ("candlestick_patterns",)
_CONFIDENCE_CEILING = 0.9
_NON_DIRECTIONAL_PATTERNS = frozenset({"doji"})


def _empty_result(symbol: str, as_of: datetime, freshness: Freshness, reason: str) -> ExpertResult:
    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Candlestick & Price Action Expert",
        council=Council.TECHNICAL,
        domain="price_action",
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


def _extract_pattern_matches(technical_result: object, warnings: List[str]) -> Optional[list]:
    """Returns the full `List[PatternMatch]`, or None if
    'candlestick_patterns' is missing, undefined, or not list-like --
    never raises."""
    try:
        patterns_output = technical_result.get("candlestick_patterns")  # type: ignore[attr-defined]
    except KeyError:
        warnings.append("required metric 'candlestick_patterns' missing from technical_analysis result")
        return None

    value = patterns_output.value
    if value is None:
        warnings.append("'candlestick_patterns' has no defined value")
        return None
    if not isinstance(value, list):
        warnings.append("'candlestick_patterns' value is not a list; cannot read detected patterns")
        return None
    return value


def compute_candlestick_expert(symbol: str, envelopes: Dict[str, EngineResultEnvelope]) -> ExpertResult:
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

    evidence: List[EvidenceItem] = []
    rule_ids: List[str] = []
    used_metrics: set = set()
    direction_signs: List[int] = []

    matches = _extract_pattern_matches(technical_result, warnings)

    if matches is not None:
        used_metrics.add("candlestick_patterns")
        if not matches:
            warnings.append("no candlestick patterns detected anywhere in the available series")
        else:
            try:
                latest_timestamp = max(match.timestamp for match in matches)
            except (TypeError, ValueError):
                warnings.append("candlestick pattern timestamps could not be compared to find the latest bar")
                latest_timestamp = None

            if latest_timestamp is not None:
                latest_matches = [match for match in matches if match.timestamp == latest_timestamp]
                for match in latest_matches:
                    rule_id = f"candlestick.{match.pattern_name}"
                    if match.pattern_name in _NON_DIRECTIONAL_PATTERNS:
                        contribution = 0.0
                    else:
                        contribution = 1.0 if match.bullish else -1.0
                        direction_signs.append(1 if match.bullish else -1)
                    evidence.append(
                        EvidenceItem(
                            metric_name="candlestick_patterns",
                            observed_value={
                                "pattern_name": match.pattern_name,
                                "timestamp": match.timestamp,
                                "bullish": match.bullish,
                            },
                            rule_id=rule_id,
                            contribution=contribution,
                        )
                    )
                    rule_ids.append(rule_id)

    conflicts: List[str] = []
    if len(direction_signs) >= 2:
        nonzero_signs = {sign for sign in direction_signs if sign != 0}
        if len(nonzero_signs) > 1:
            conflicts.append("multiple candlestick patterns on the latest matched bar disagree on direction")

    normalized_score: Optional[float]
    if direction_signs:
        average_sign = sum(direction_signs) / len(direction_signs)
        normalized_score = max(-1.0, min(1.0, average_sign))
    else:
        normalized_score = None

    # Only one required metric exists for this expert (unlike Trend's four
    # or Volume's two), so `available_count` is always 0 or 1 -- PARTIAL
    # is not a reachable state and is deliberately not modeled as a branch.
    required_count = len(_REQUIRED_METRICS)
    available_count = len(used_metrics)
    completeness = DataCompleteness.COMPLETE if available_count == required_count else DataCompleteness.INSUFFICIENT

    # Every contributing sign is always exactly +1 or -1 (never 0 -- unlike
    # Trend's EMA-vs-SMA tie case), so whenever direction_signs is non-empty
    # and there is no conflict, normalized_score is guaranteed nonzero: a
    # final "still NEUTRAL" fallback branch would be unreachable dead code
    # in this expert's specific domain and is deliberately not modeled.
    if not direction_signs:
        direction = ExpertDirection.NEUTRAL
    elif conflicts:
        direction = ExpertDirection.MIXED
    elif normalized_score is not None and normalized_score > 0.0:
        direction = ExpertDirection.BULLISH
    else:
        direction = ExpertDirection.BEARISH

    if not direction_signs:
        confidence = 0.0
    else:
        completeness_factor = available_count / required_count
        if conflicts:
            # Disagreement is punished harder than agreement is rewarded (BIIC Article III.3).
            agreement_factor = 0.4
        elif len(direction_signs) < 2:
            # Only one directional pattern matched -- agreement can't be confirmed either way.
            agreement_factor = 0.7
        else:
            agreement_factor = 1.0
        confidence = max(0.0, min(_CONFIDENCE_CEILING, completeness_factor * agreement_factor))

    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Candlestick & Price Action Expert",
        council=Council.TECHNICAL,
        domain="price_action",
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
            "the 'latest' matched bar is the most recent bar that matched ANY pattern, which "
            "may be older than the true latest bar in the underlying series if recent bars "
            "matched no pattern -- this expert has no access to the true latest bar's "
            "timestamp to detect or disclose that gap (see module docstring, Architectural "
            "Decision 4)",
            "Doji detections are reported as evidence but never contribute directionally -- "
            "a Doji's textbook meaning is indecision, not direction, unlike the other four "
            "patterns detected here (see module docstring, Architectural Decision 2)",
            "no magnitude/strength signal exists at the pattern-detection layer (PatternMatch "
            "carries no numeric field, e.g. wick-to-body ratio); normalized_score is the plain "
            "average of contributing patterns' signs, never scaled by an invented intensity "
            "measure, unlike Trend Expert's ADX scaling or Volume Expert's relative-volume "
            "transform (see module docstring, Architectural Decision 3)",
            "patterns are detected as context-free bar geometry only (candlestick_patterns.py's "
            "own documented simplification) -- e.g. a Hammer here means 'this bar's shape "
            "matches the classical pattern,' not 'a confirmed reversal is occurring after a "
            "prior downtrend,' since trend context would require reading another expert's "
            "metrics and is deliberately out of scope to avoid cross-expert double-counting",
        ),
        version="1.0.0",
        metadata={},
    )


DEFAULT_EXPERT_REGISTRY.register(
    ExpertSpec(
        expert_id=EXPERT_ID,
        name="Candlestick & Price Action Expert",
        council=Council.TECHNICAL,
        domain="price_action",
        version="1.0.0",
        status=ExpertStatus.EXPERIMENTAL,
        required_engines=["technical_analysis"],
        contributing_metrics=list(_REQUIRED_METRICS),
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=compute_candlestick_expert,
    )
)
