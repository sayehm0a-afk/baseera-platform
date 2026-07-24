"""Shared value types for the Decision & Intelligence Modules contracts.

See this package's `__init__.py` for the full scope statement. As with
`src.core.autonomous_intelligence_layer.contracts.types` and
`src.analysis.core.contracts.AnalysisOutput`, most fields that carry a
module-specific internal shape (`payload`, `reasons`, `criteria`) are
typed loosely (`Mapping[str, Any]` / `Tuple[str, ...]`) rather than
given a fixed schema -- designing exactly what a scan filter, a
recommendation's reasoning payload, or a risk factor breakdown
contains is real design work for whichever future, separately-approved
milestone implements a concrete module, not something to invent here.

`MANDATORY_DISCLAIMER_AR`/`_EN` are the one piece of fixed, non-generic
content in this module, deliberately: Phase 9's explicit instruction --
"لا تضع ادعاءات مضمونة بالأرباح... أضف تنبيهًا واضحًا أن النتائج
تحليلية وليست توصية مالية ملزمة" ("no guaranteed-profit claims... add
a clear notice that results are analytical, not a binding financial
recommendation") -- is encoded as a required field on every
human-facing output type below, not left to each future implementation
to remember or phrase differently.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Tuple

MANDATORY_DISCLAIMER_AR = (
    "هذا تحليل آلي مبني على بيانات متاحة وقت إصداره، وليس توصية مالية "
    "ملزمة ولا ضماناً لأي ربح أو عائد. اتخذ قرارك الاستثماري بعد استشارة "
    "مختص مرخص وبناءً على تحمّلك الشخصي للمخاطر."
)

MANDATORY_DISCLAIMER_EN = (
    "This is an automated analysis based on data available at the time "
    "it was produced. It is not a binding financial recommendation and "
    "carries no guarantee of profit or return. Consult a licensed "
    "professional and consider your own risk tolerance before acting."
)


class RecommendationVerdict(str, Enum):
    """The five verdict categories Phase 9 explicitly names, kept as
    the exact five values instructed -- no additional category was
    invented, and none of the five was renamed."""

    WATCH = "watch"  # مراقبة
    SUITABLE_FOR_SPECULATION = "suitable_for_speculation"  # مناسب للمضاربة
    SUITABLE_FOR_INVESTMENT = "suitable_for_investment"  # مناسب للاستثمار
    WAIT = "wait"  # انتظار
    AVOID_TEMPORARILY = "avoid_temporarily"  # تجنب مؤقت


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class DataState(str, Enum):
    """Whether the data a module's output is based on was live, cached,
    or degraded -- the type-level hook for Phase 8's "شاشة حالة
    البيانات: Live أو Cached" requirement, so every output produced by
    a future concrete module can honestly report which state it saw,
    rather than the API layer having to guess after the fact."""

    LIVE = "live"
    CACHED = "cached"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ScanCriteria:
    """What a Live Market Scanner is asked to look for. `filters` is
    unconstrained (e.g. "RSI < 30", "volume > 20-day average") --
    designing a filter DSL is a future module's own concern."""

    filters: Mapping[str, Any]
    universe: Tuple[str, ...] = ()  # empty = every known symbol
    max_results: Optional[int] = None


@dataclass(frozen=True)
class ScanMatch:
    symbol: str
    matched_at: datetime
    reasons: Tuple[str, ...]
    data_state: DataState
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationOutput:
    """The Recommendation Engine's output envelope -- every field
    Phase 9 explicitly lists: verdict, confidence, reasons, risks,
    time horizon, support/resistance, targets, data state, as_of, and
    the mandatory disclaimer."""

    symbol: str
    verdict: RecommendationVerdict
    confidence: float  # [0.0, 1.0] -- meaning is owned by the concrete engine, not fixed here
    reasons: Tuple[str, ...]
    risks: Tuple[str, ...]
    time_horizon: TimeHorizon
    support_levels: Tuple[float, ...]
    resistance_levels: Tuple[float, ...]
    initial_targets: Tuple[float, ...]
    data_state: DataState
    as_of: datetime
    disclaimer_ar: str = MANDATORY_DISCLAIMER_AR
    disclaimer_en: str = MANDATORY_DISCLAIMER_EN
    supporting_data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    quantity: float
    average_cost: float


@dataclass(frozen=True)
class PortfolioAnalysisResult:
    positions: Tuple[PortfolioPosition, ...]
    total_value: Optional[float]
    concentration_warnings: Tuple[str, ...]
    risk_level: RiskLevel
    as_of: datetime
    disclaimer_ar: str = MANDATORY_DISCLAIMER_AR
    disclaimer_en: str = MANDATORY_DISCLAIMER_EN
    breakdown: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskAssessment:
    symbol: Optional[str]  # None for a portfolio- or market-level assessment
    risk_level: RiskLevel
    factors: Tuple[str, ...]
    as_of: datetime
    disclaimer_ar: str = MANDATORY_DISCLAIMER_AR
    disclaimer_en: str = MANDATORY_DISCLAIMER_EN
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    symbol: str
    condition: Mapping[str, Any]  # e.g. {"field": "price", "op": ">=", "value": 42.0}
    severity: AlertSeverity


@dataclass(frozen=True)
class AlertEvent:
    rule_id: str
    symbol: str
    severity: AlertSeverity
    message: str
    triggered_at: datetime
    data_state: DataState
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionContext:
    """What the AI Decision Layer receives: already-computed output
    from other modules in this package (and, transitively, from
    Council/Composite/live data), never raw provider data directly --
    the same "consumes already-computed results" discipline
    `IntelligenceContext` (AIL contracts) already establishes."""

    symbol: str
    recommendation: Optional[RecommendationOutput]
    risk_assessment: Optional[RiskAssessment]
    portfolio_context: Optional[PortfolioAnalysisResult]
    as_of: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionOutput:
    symbol: str
    verdict: RecommendationVerdict
    confidence: float
    reasoning: Tuple[str, ...]
    as_of: datetime
    disclaimer_ar: str = MANDATORY_DISCLAIMER_AR
    disclaimer_en: str = MANDATORY_DISCLAIMER_EN
