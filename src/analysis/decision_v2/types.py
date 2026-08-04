"""Shared types for Decision Engine V2."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class Decision(str, Enum):
    """The user-facing action taxonomy Phase 1 requires -- deliberately
    distinct from `Recommendation` (STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL,
    src.analysis.recommendation.types), which stays as the underlying
    score-band classification `RecommendationEngine` produces. This
    enum answers "what should the user actually do right now," which
    depends on the gates below, not on the score band alone -- e.g. a
    STRONG_BUY score whose price has already run past a sane entry
    zone becomes WAIT_FOR_ENTRY here, not STRONG_BUY_CANDIDATE."""

    STRONG_BUY_CANDIDATE = "STRONG_BUY_CANDIDATE"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    WAIT_FOR_ENTRY = "WAIT_FOR_ENTRY"
    WATCH = "WATCH"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


DECISION_LABELS_AR = {
    Decision.STRONG_BUY_CANDIDATE: "فرصة شراء قوية",
    Decision.BUY_CANDIDATE: "فرصة مناسبة للشراء",
    Decision.WAIT_FOR_ENTRY: "انتظر دخولًا أفضل",
    Decision.WATCH: "مناسب للمراقبة",
    Decision.HOLD: "احتفاظ",
    Decision.REDUCE: "تخفيف الكمية",
    Decision.EXIT: "خروج",
    Decision.REJECT: "غير مناسب حاليًا",
    Decision.INSUFFICIENT_DATA: "البيانات غير كافية",
}

CONFIDENCE_DISCLAIMER_AR = (
    "درجة الثقة تقيس قوة وتوافق الأدلة المتاحة، ولا تعني ضمان تحقق الهدف."
)

ANALYSIS_DISCLAIMER_AR = (
    "هذا تحليل آلي مساعد مبني على البيانات المتاحة، وليس ضمانًا للربح أو بديلًا عن "
    "قرار المستخدم وإدارة المخاطر."
)


class DataFreshnessStatus(str, Enum):
    LIVE = "LIVE"
    LAST_SESSION = "LAST_SESSION"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SubScores:
    """Every sub-score is 0-100, 50 = neutral, computed from real
    already-available indicator values (see scoring.py for the exact,
    documented formula behind each one -- no unexplained magic numbers
    live outside that module)."""

    trend_score: Optional[float]
    momentum_score: Optional[float]
    volume_score: Optional[float]
    liquidity_score: Optional[float]
    volatility_score: Optional[float]
    risk_reward_score: Optional[float]
    market_context_score: Optional[float]
    data_quality_score: float


@dataclass(frozen=True)
class GateOutcome:
    """One publication-gate check (see gates.py). `blocking=True` means
    a FAIL here forces the decision to REJECT/INSUFFICIENT_DATA/
    WAIT_FOR_ENTRY/WATCH regardless of the underlying score -- the same
    "evidence overrides score" principle
    src.market_intelligence.publication_gate already established for
    the market-wide scanner, applied here uniformly to single-stock
    analysis too."""

    name: str
    passed: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class DecisionResult:
    symbol: str
    company_name_ar: Optional[str]
    company_name_en: str
    sector_ar: Optional[str]

    decision: Decision
    decision_label_ar: str

    confidence_score: float
    opportunity_quality_score: float
    risk_score: float
    data_quality_score: float
    data_freshness_status: DataFreshnessStatus

    current_price: Optional[float]
    entry_zone_low: Optional[float]
    entry_zone_high: Optional[float]
    stop_loss: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    target_3: Optional[float]

    expected_return_target_1: Optional[float]
    expected_return_target_2: Optional[float]
    downside_to_stop: Optional[float]
    risk_reward_target_1: Optional[float]
    risk_reward_target_2: Optional[float]

    expected_holding_period_min_days: Optional[int]
    expected_holding_period_max_days: Optional[int]
    expected_holding_period_label_ar: str
    horizon_type: str

    market_status: str
    decision_timestamp: datetime

    invalidation_conditions: List[str]
    positive_reasons: List[str]
    negative_reasons: List[str]
    warnings: List[str]
    recommendation_basis: str

    analysis_version: str
    data_source: str
    scan_run_id: Optional[int]

    sub_scores: SubScores
    gates: List[GateOutcome] = field(default_factory=list)
