"""Volume Expert: Technical Council's fourth BEIF expert (M2.10),
following the same architectural shape Trend Expert (M2.7), Momentum
Expert (M2.8), and Volatility Expert (M2.9) established -- with one
genuinely new departure from all three: Volume Expert is the first
Technical Council expert that must read more than an indicator's
single latest value to produce any evidence at all.

Reads only the already-computed obv/volume_sma_20 indicator outputs
from a supplied "technical_analysis" engine result envelope -- never a
raw OHLCV DataFrame, never recomputes On-Balance Volume or the volume
moving average itself (BEIF Section 14's anti-duplication rule).

======================================================================
ARCHITECTURAL DECISION 1: reading an indicator's full series, not just
its latest() value -- and why this does not violate BEIF Section 14
======================================================================
On-Balance Volume (`src/analysis/volume/volume_indicators.py::obv`) is
a *cumulative running total*: `OBV[t] = OBV[t-1] +/- volume[t]`. A
single OBV value at one point in time carries no directional
information on its own -- "OBV is 5,230,000" means nothing without a
reference point elsewhere in the same series to compare it against.
Trend/Momentum/Volatility Expert could all answer their questions from
a single already-computed snapshot (`IndicatorOutput.latest()`)
because their underlying indicators (moving averages, RSI, MACD,
Bollinger Bands, ATR) are each already a function of a rolling window,
re-expressed as one current value. OBV has no such built-in windowing.

This expert therefore reads `IndicatorOutput.value` directly (the full
`pd.Series` OBV's own registered `IndicatorSpec.compute` already
produced) and looks back a fixed number of bars within that
already-computed series. This is **not** a violation of BEIF Section
14's anti-duplication rule: that rule prohibits recomputing an
indicator from raw OHLCV, or reading raw price/volume data directly --
it does not restrict how much of an *already-computed* indicator's own
output an expert may read. `IndicatorOutput.latest()` was always a
convenience view over `IndicatorOutput.value`, never the only
legitimate one.

======================================================================
ARCHITECTURAL DECISION 2: the lookback window is 20 bars, matching
volume_sma_20's own window, not an arbitrary number
======================================================================
OBV's directional evidence is computed as `sign(OBV[latest] -
OBV[latest - 20])` -- net accumulation or distribution over the same
20-bar window `volume_sma_20` itself already covers. This keeps both
pieces of evidence describing the same time horizon, a deliberate,
disclosed choice, not an unexplained magic number. If fewer than 21
data points are available, OBV trend direction cannot be computed at
all (disclosed via `warnings`), and this expert -- unlike Trend/
Momentum Expert, which each had two independent directional sources --
has **only one** directional evidence source in v1. There is
therefore nothing for it to disagree with, and `conflicts` is always
empty by construction: not because two sources agreed, but because a
second, independent volume-direction signal is not available from the
currently registered indicator set. This is disclosed explicitly,
never silently implied as "no disagreement found."

Because OBV's absolute delta has no universal, non-fabricated scale
(the same problem MACD's histogram magnitude posed for Momentum
Expert), the OBV-trend contribution is sign-only (+/-1), never scaled
by its own magnitude.

======================================================================
ARCHITECTURAL DECISION 3: recovering the latest bar's raw volume from
OBV's own construction, never inventing a "current volume" figure
======================================================================
No raw, single-bar "current volume" `IndicatorOutput` is registered in
`IndicatorRegistry` -- only `volume_sma_20` (a 20-period average) and
`obv` (a cumulative total) exist. Comparing "current volume" to its
own recent average is nonetheless possible without fabricating a
number, because OBV's own construction already encodes it: by
definition, `OBV[t] - OBV[t-1] = sign(close[t] - close[t-1]) *
volume[t]`, so `abs(OBV[t] - OBV[t-1])` recovers `volume[t]` exactly
whenever `sign(close[t] - close[t-1])` is nonzero. This is arithmetic
recovery of a value already implicit in an already-computed indicator,
not a new computation over raw data, and not an invented figure.

**Known, disclosed limitation of this recovery**: when the latest
bar's close is unchanged from the prior bar (`sign == 0`), OBV's own
definition leaves it unchanged regardless of how much volume actually
traded that bar -- the recovered value reads exactly `0.0` in that
case, understating true volume. This is OBV's own well-known blind
spot, not an artifact of this expert's arithmetic, and is disclosed on
every result via `limitations`, with a specific `warnings` entry
whenever it is actually encountered.

The recovered volume is then expressed as a dimensionless ratio to
`volume_sma_20.latest()` and passed through the bounded transform
`ratio / (1 + ratio)` -- a standard, parameter-free monotonic mapping
of `[0, infinity)` onto `[0, 1)`, chosen specifically because it
requires no invented threshold: a ratio of exactly 1.0 (current volume
equal to its own 20-period average) maps to the middle of the range
(0.5), never to an asserted "elevated" or "quiet" classification. This
mirrors Volatility Expert's identical refusal (M2.9) to assert a
calibrated compressed/expanded threshold without empirical support.

Confidence is capped below 1.0 unconditionally (Document 1 Section 13,
BIIC Article IV.4), identical to every prior Technical Council expert.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertSpec
from src.analysis.experts.types import Council, EvidenceItem, ExpertDirection, ExpertResult, ExpertStatus

EXPERT_ID = "technical.volume"
_REQUIRED_METRICS: Tuple[str, ...] = ("obv", "volume_sma_20")
_CONFIDENCE_CEILING = 0.9
_OBV_TREND_LOOKBACK_BARS = 20
_DEFAULT_STRENGTH_WHEN_UNAVAILABLE = 0.5


def _empty_result(symbol: str, as_of: datetime, freshness: Freshness, reason: str) -> ExpertResult:
    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Volume Expert",
        council=Council.TECHNICAL,
        domain="volume",
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


def _extract_obv_series(technical_result: object, warnings: List[str]) -> Optional[object]:
    """Returns the full OBV pd.Series, or None if 'obv' is missing,
    undefined, or not series-like -- never raises."""
    try:
        obv_output = technical_result.get("obv")
    except KeyError:
        warnings.append("required metric 'obv' missing from technical_analysis result")
        return None

    value = obv_output.value
    if value is None:
        warnings.append("'obv' has no defined value")
        return None
    if not hasattr(value, "iloc") or not hasattr(value, "__len__"):
        warnings.append("'obv' value is not a Series-like object; cannot read historical points")
        return None
    return value


def compute_volume_expert(symbol: str, envelopes: Dict[str, EngineResultEnvelope]) -> ExpertResult:
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
    strength: Optional[float] = None

    obv_series = _extract_obv_series(technical_result, warnings)

    # --- Rule 1: OBV trend direction over the last _OBV_TREND_LOOKBACK_BARS bars ---
    if obv_series is not None:
        if len(obv_series) < _OBV_TREND_LOOKBACK_BARS + 1:
            warnings.append(
                f"'obv' has fewer than {_OBV_TREND_LOOKBACK_BARS + 1} data points "
                f"({len(obv_series)} available); cannot compute a {_OBV_TREND_LOOKBACK_BARS}-bar trend"
            )
        else:
            try:
                latest_obv = float(obv_series.iloc[-1])
                lookback_obv = float(obv_series.iloc[-(_OBV_TREND_LOOKBACK_BARS + 1)])
            except (TypeError, ValueError):
                warnings.append("'obv' series values could not be read as numeric")
            else:
                delta = latest_obv - lookback_obv
                sign = 1 if delta > 0 else (-1 if delta < 0 else 0)
                rule_id = "volume.obv_trend_direction"
                evidence.append(
                    EvidenceItem(
                        metric_name="obv",
                        observed_value={
                            "latest": latest_obv,
                            f"lookback_{_OBV_TREND_LOOKBACK_BARS}_bars_ago": lookback_obv,
                        },
                        rule_id=rule_id,
                        contribution=float(sign),
                    )
                )
                rule_ids.append(rule_id)
                used_metrics.add("obv")
                direction_signs.append(sign)

    # --- Rule 2: relative volume (recovered latest-bar volume vs. its 20-period average) ---
    if obv_series is not None and len(obv_series) >= 2:
        try:
            latest_obv = float(obv_series.iloc[-1])
            prior_obv = float(obv_series.iloc[-2])
        except (TypeError, ValueError):
            warnings.append("'obv' series values could not be read as numeric for volume recovery")
        else:
            recovered_volume = abs(latest_obv - prior_obv)
            if recovered_volume == 0.0:
                warnings.append(
                    "recovered latest-bar volume is exactly zero -- either genuinely no volume "
                    "traded, or the latest bar's close was unchanged from the prior bar, which "
                    "OBV's own construction cannot distinguish from zero volume (a known, "
                    "disclosed limitation of this recovery method, see module docstring)"
                )

            try:
                volume_sma_output = technical_result.get("volume_sma_20")
            except KeyError:
                warnings.append("required metric 'volume_sma_20' missing from technical_analysis result")
                volume_sma_output = None

            if volume_sma_output is not None:
                volume_sma_latest = volume_sma_output.latest()
                if volume_sma_latest is None:
                    warnings.append("required metric 'volume_sma_20' had no defined latest value")
                else:
                    volume_sma_latest = float(volume_sma_latest)
                    if volume_sma_latest <= 0.0:
                        warnings.append(
                            "'volume_sma_20' is zero or negative; cannot compute a relative-volume ratio"
                        )
                    else:
                        ratio = recovered_volume / volume_sma_latest
                        strength = ratio / (1.0 + ratio)
                        rule_id = "volume.relative_volume_vs_average"
                        evidence.append(
                            EvidenceItem(
                                metric_name="volume_sma_20",
                                observed_value={
                                    "recovered_latest_volume": recovered_volume,
                                    "volume_sma_20": volume_sma_latest,
                                    "ratio": ratio,
                                },
                                rule_id=rule_id,
                                contribution=strength,
                            )
                        )
                        rule_ids.append(rule_id)
                        used_metrics.add("volume_sma_20")

    normalized_score: Optional[float]
    if direction_signs:
        effective_strength = strength if strength is not None else _DEFAULT_STRENGTH_WHEN_UNAVAILABLE
        normalized_score = max(-1.0, min(1.0, float(direction_signs[0]) * effective_strength))
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

    if normalized_score is None:
        direction = ExpertDirection.NEUTRAL
        confidence = 0.0
    else:
        if normalized_score > 0.0:
            direction = ExpertDirection.BULLISH
        elif normalized_score < 0.0:
            direction = ExpertDirection.BEARISH
        else:
            direction = ExpertDirection.NEUTRAL
        completeness_factor = available_count / required_count
        # Only one directional evidence source exists in v1 (see module
        # docstring, Architectural Decision 2) -- "agreement" here means the
        # magnitude-only relative-volume rule also contributed, not that two
        # directional sources agreed, since there is only ever one.
        agreement_factor = 1.0 if strength is not None else 0.7
        confidence = max(0.0, min(_CONFIDENCE_CEILING, completeness_factor * agreement_factor))

    return ExpertResult(
        expert_id=EXPERT_ID,
        expert_name="Volume Expert",
        council=Council.TECHNICAL,
        domain="volume",
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
        conflicts=(),
        limitations=(
            "only one directional evidence source (OBV's own 20-bar trend) exists in v1; "
            "conflicts is always empty because there is nothing else to compare it against, "
            "not because two sources agreed -- a second, independent volume-direction signal "
            "is not available from the currently registered indicator set",
            "relative volume is derived by recovering the latest bar's raw volume from OBV's "
            "own construction (|OBV[t] - OBV[t-1]|); this reads as exactly zero whenever the "
            "latest bar's close was unchanged from the prior bar, understating true volume in "
            "that specific case -- a known limitation of OBV itself, not of this expert's "
            "arithmetic (see module docstring, Architectural Decision 3)",
            "relative volume's [0, 1) mapping (ratio / (1 + ratio)) is a parameter-free "
            "mathematical transform, not a calibrated 'elevated volume' classification -- no "
            "empirically-supported threshold for that classification exists yet (Document 1 "
            "Section 10, Document 7), mirroring Volatility Expert's identical refusal (M2.9)",
        ),
        version="1.0.0",
        metadata={},
    )


DEFAULT_EXPERT_REGISTRY.register(
    ExpertSpec(
        expert_id=EXPERT_ID,
        name="Volume Expert",
        council=Council.TECHNICAL,
        domain="volume",
        version="1.0.0",
        status=ExpertStatus.EXPERIMENTAL,
        required_engines=["technical_analysis"],
        contributing_metrics=list(_REQUIRED_METRICS),
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=compute_volume_expert,
    )
)
