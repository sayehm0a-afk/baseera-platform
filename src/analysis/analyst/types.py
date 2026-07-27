"""Shared types for the Autonomous AI Analyst Framework.

This framework is a *narration* layer, not a fourth analysis/decision
engine: it never recomputes an indicator, a ratio, a score, or a price
target -- it only reads what `TechnicalAnalysisEngine`,
`FundamentalAnalysisEngine`, `RecommendationEngine`, and
`AIDecisionEngine` already produced (via one `InvestmentDecision`, the
AI Decision Intelligence Layer's own final output) and turns it into
human-quality investment reasoning: an `Explanation` with the twelve
sections a professional analyst report is expected to contain.

`Evidence` is the framework's own extension point, exactly the role
`AnalysisContext`/`ScoreContribution` play one layer down: every stage
of the `ReasoningPipeline` (signal interpretation, conflict resolution,
confidence narration, prose generation) reads only from `Evidence`,
never from `AnalysisContext`/`InvestmentDecision` directly, so a future
stage that needs more raw material can be satisfied by widening
`Evidence` without touching the stages that already work.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from src.analysis.decision.types import DecisionFactorBreakdown, InvestmentDecision
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult
from src.analysis.recommendation.types import Signal, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult


class FactorStrength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    MILD = "MILD"


class ConfidenceBand(str, Enum):
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"


class TensionLevel(str, Enum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


@dataclass(frozen=True)
class Evidence:
    """Everything the reasoning pipeline is allowed to narrate from --
    the framework's own `AnalysisContext` equivalent. Assembled once by
    `EvidenceCollector` from an `AnalysisContext` plus the
    `InvestmentDecision` `AIDecisionEngine` already computed for it, so
    every later stage works from one frozen, self-consistent snapshot
    rather than re-reading (and risking re-deriving) the source engines.
    """

    symbol: str
    decision: InvestmentDecision
    technical_result: Optional[TechnicalAnalysisResult]
    fundamental_result: Optional[FundamentalAnalysisResult]
    signals: List[Signal] = field(default_factory=list)
    contributor_breakdown: List[DecisionFactorBreakdown] = field(default_factory=list)

    @property
    def technical_available(self) -> bool:
        return self.technical_result is not None

    @property
    def fundamental_available(self) -> bool:
        return self.fundamental_result is not None


@dataclass(frozen=True)
class InterpretedFactor:
    """One signal, reframed as a plain-language investment factor --
    what `SignalInterpreter` turns each `Signal` in `Evidence.signals`
    into. `category` is the same display label
    `DecisionFactorBreakdown.category` already uses (e.g. "Technical
    Analysis"), so factors and category tilts speak the same
    vocabulary."""

    category: str
    description: str
    direction: SignalDirection
    strength: FactorStrength
    impact: float


@dataclass(frozen=True)
class InterpretedSignals:
    """`SignalInterpreter`'s full output: every signal sorted into
    bullish/bearish/neutral by direction and, within bullish/bearish,
    by descending `abs(impact)` -- the order `NarrativeBuilder` and
    `RecommendationComposer` cite factors in. `category_tilts` is one
    label per contributor category ("bullish"/"bearish"/"neutral"/
    "unavailable"), derived from `Evidence.contributor_breakdown`, and
    is what `ConflictResolver` compares across categories."""

    bullish_factors: List[InterpretedFactor]
    bearish_factors: List[InterpretedFactor]
    neutral_factors: List[InterpretedFactor]
    category_tilts: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConflictAssessment:
    """Whether the evidence pulls in different directions at once (e.g.
    strong technical momentum against weak fundamentals) -- an honest
    "the picture isn't unanimous" disclosure a real analyst would give,
    rather than presenting a single blended score as if every input
    agreed."""

    has_conflict: bool
    tension_level: TensionLevel
    conflicting_categories: List[Tuple[str, str]]
    narrative: str
    alternative_scenarios: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfidenceAssessment:
    """A plain-language band and explanation for `InvestmentDecision.
    confidence`, which this framework only narrates -- it never
    recomputes the number itself."""

    confidence: float
    band: ConfidenceBand
    narrative: str


@dataclass(frozen=True)
class RecommendationRationale:
    """The investment-summary and final-rationale prose --
    `RecommendationComposer`'s output, assembled last since it
    synthesizes every earlier stage's findings into the report's
    headline paragraphs."""

    summary: str
    final_rationale: str


@dataclass(frozen=True)
class Explanation:
    """The complete, twelve-section human-quality explanation
    `ReasoningPipeline` produces for one `InvestmentDecision`. Every
    field is always populated, even when the underlying data was
    unavailable (in which case the text says so honestly) -- a
    consumer never has to guard against a missing section."""

    investment_summary: str
    technical_reasoning: str
    fundamental_reasoning: str
    risk_explanation: str
    bullish_factors: List[str]
    bearish_factors: List[str]
    confidence_explanation: str
    target_price_explanation: str
    stop_loss_explanation: str
    time_horizon_explanation: str
    alternative_scenarios: List[str]
    final_recommendation_rationale: str


@dataclass(frozen=True)
class AnalystReport:
    """`AnalystEngine.analyze()`'s final output for one symbol: the
    `InvestmentDecision` it was built from (nothing here duplicates or
    overrides that decision) plus the narrated `Explanation`."""

    symbol: str
    decision: InvestmentDecision
    explanation: Explanation
    generated_at: datetime
    engine_version: str
