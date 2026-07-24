"""Shared types for the Composite Intelligence Engine.

Neither TechnicalAnalysisResult (M2.2) nor FundamentalAnalysisResult
(M2.3) carries an "as of" timestamp -- rather than retrofit one into
either already-merged engine (which would be "modifying an existing
engine merely to force symmetry," explicitly ruled out), freshness is
modeled externally here, via EngineResultEnvelope. CompositeFactorOutput
and CompositeResult satisfy src.analysis.core.contracts' AnalysisOutput/
AnalysisEngineResult structurally, the same technique IndicatorOutput
(M2.2) and RatioOutput (M2.3) already use -- so a future Signal Engine
can consume CompositeResult exactly like Composite consumes each
engine's result today, without any of this changing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class Freshness(str, Enum):
    """How recent an engine's result is, relative to a documented
    default staleness policy (see classify_freshness). Informational
    only in M2.4 -- it does not block fusion; different engines have
    inherently different natural cadences (daily bars vs. quarterly/
    annual filings), and a hard global age gate would itself be a
    premature Signal-Engine-level policy decision."""

    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


class DataCompleteness(str, Enum):
    """How much of a composite factor's required input was actually
    available and usable."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class Agreement(str, Enum):
    """Whether the engines contributing to a factor pointed the same
    direction. UNKNOWN when agreement isn't a meaningful concept for
    that particular factor (e.g. a purely contextual, non-directional
    factor) -- not the same as DISAGREE."""

    AGREE = "agree"
    DISAGREE = "disagree"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CompositeCategory(str, Enum):
    """Classification of a composite factor. Deliberately small and
    non-directional -- these describe what *kind* of cross-engine
    relationship a factor expresses, not a trading opinion."""

    ALIGNMENT = "alignment"
    CONTEXT = "context"
    DATA_QUALITY = "data_quality"


DEFAULT_FRESH_WITHIN = timedelta(days=1)
DEFAULT_AGING_WITHIN = timedelta(days=30)


def classify_freshness(
    as_of: datetime,
    now: Optional[datetime] = None,
    fresh_within: timedelta = DEFAULT_FRESH_WITHIN,
    aging_within: timedelta = DEFAULT_AGING_WITHIN,
) -> Freshness:
    """The documented default staleness policy: FRESH within
    `fresh_within` of `now`, AGING within `aging_within`, STALE beyond
    that. Callers needing a different policy for a particular engine
    (e.g. quarterly fundamentals are expected to be weeks old) should
    pass their own `fresh_within`/`aging_within` rather than treating
    this default as universal.
    """
    reference = now if now is not None else datetime.now(as_of.tzinfo)
    age = reference - as_of
    if age < timedelta(0):
        return Freshness.UNKNOWN
    if age <= fresh_within:
        return Freshness.FRESH
    if age <= aging_within:
        return Freshness.AGING
    return Freshness.STALE


@dataclass(frozen=True)
class EngineResultEnvelope:
    """Pairs an already-computed AnalysisEngineResult-conforming object
    with the metadata Composite needs but the result itself doesn't
    carry."""

    engine_name: str
    result: Any  # structurally an AnalysisEngineResult
    as_of: datetime
    freshness: Freshness


def build_envelope(
    engine_name: str,
    result: Any,
    as_of: datetime,
    now: Optional[datetime] = None,
    fresh_within: timedelta = DEFAULT_FRESH_WITHIN,
    aging_within: timedelta = DEFAULT_AGING_WITHIN,
) -> EngineResultEnvelope:
    """Convenience constructor: computes freshness via the default
    policy instead of requiring every caller to call
    classify_freshness() by hand."""
    freshness = classify_freshness(as_of, now=now, fresh_within=fresh_within, aging_within=aging_within)
    return EngineResultEnvelope(engine_name=engine_name, result=result, as_of=as_of, freshness=freshness)


@dataclass(frozen=True)
class CompositeFactorOutput:
    """Uniform wrapper around one computed composite factor's result.

    Satisfies src.analysis.core.contracts.AnalysisOutput structurally
    (name, category, value, .latest()) without importing that module --
    same technique IndicatorOutput/RatioOutput already use.

    Unlike IndicatorOutput/RatioOutput, this also carries completeness/
    agreement/contributing_engines/explanation -- a composite factor
    fuses multiple, independently-partial sources, so a bare value
    isn't informative enough on its own about *why* it is what it is.
    `explanation` is structured data (raw inputs + a machine-readable
    rule id), not prose -- generating human-readable text from it is
    a future Explainable AI Engine's job, not this one's.
    """

    name: str
    category: CompositeCategory
    value: Optional[float]
    completeness: DataCompleteness
    agreement: Optional[Agreement]
    contributing_engines: List[str]
    explanation: Dict[str, Any]

    def latest(self) -> Any:
        return self.value


CompositeFactorMap = Dict[str, CompositeFactorOutput]


@dataclass(frozen=True)
class CompositeResult:
    """The result of running every registered composite factor against
    one set of engine result envelopes.

    Satisfies src.analysis.core.contracts.AnalysisEngineResult
    structurally -- a future Signal Engine can consume this exactly
    like Composite consumes each engine's result today, recursively,
    without this class or the contract changing.
    """

    factors: CompositeFactorMap = field(default_factory=dict)

    def get(self, name: str) -> CompositeFactorOutput:
        return self.factors[name]

    def latest_snapshot(self) -> Dict[str, Any]:
        return {name: output.latest() for name, output in self.factors.items()}
