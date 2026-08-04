"""Shared types for Decision Engine V2."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


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
    # Phase 2A canonical Arabic taxonomy (Product Owner spec). The
    # underlying `Decision` enum values themselves are unchanged and
    # remain the stable, machine-readable identifiers every existing
    # caller (routes, tests, DecisionV2Snapshot rows) already depends
    # on -- only this display-label mapping changed. "شراء مشروط"
    # (conditional buy) is intentionally not a 10th enum value: that
    # nuance is carried by the separate `entry_status` field (e.g.
    # BUY_CANDIDATE + CONDITIONAL_ON_BREAKOUT), so there is still only
    # one canonical decision taxonomy, not two overlapping ones.
    Decision.STRONG_BUY_CANDIDATE: "شراء قوي",
    Decision.BUY_CANDIDATE: "شراء",
    Decision.WAIT_FOR_ENTRY: "انتظار",
    Decision.WATCH: "مراقبة",
    Decision.HOLD: "احتفاظ",
    Decision.REDUCE: "تخفيف",
    Decision.EXIT: "خروج",
    Decision.REJECT: "رفض التوصية",
    Decision.INSUFFICIENT_DATA: "بيانات غير كافية",
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


class TradeType(str, Enum):
    """The eight trade-duration classifications the Phase 2A brief
    requires. `SCALP`/`INTRADAY` are defined for API/forward
    compatibility but never assigned by `trade_classification.py` --
    this platform ingests daily bars only, so a same-session scalp or
    day-trade classification would have no real evidence behind it.
    See that module's docstring for exactly which of the eight are
    currently reachable and why."""

    SCALP = "SCALP"
    INTRADAY = "INTRADAY"
    SHORT_SWING_2_5_DAYS = "SHORT_SWING_2_5_DAYS"
    WEEKLY_SWING = "WEEKLY_SWING"
    SWING_TRADE = "SWING_TRADE"
    MONTHLY_INVESTMENT = "MONTHLY_INVESTMENT"
    MEDIUM_TERM_INVESTMENT = "MEDIUM_TERM_INVESTMENT"
    LONG_TERM_INVESTMENT = "LONG_TERM_INVESTMENT"


TRADE_TYPE_LABELS_AR = {
    TradeType.SCALP: "مضاربة لحظية",
    TradeType.INTRADAY: "مضاربة يومية",
    TradeType.SHORT_SWING_2_5_DAYS: "مضاربة من يومين إلى خمسة أيام",
    TradeType.WEEKLY_SWING: "مضاربة أسبوعية",
    TradeType.SWING_TRADE: "تداول متأرجح",
    TradeType.MONTHLY_INVESTMENT: "استثمار شهري",
    TradeType.MEDIUM_TERM_INVESTMENT: "استثمار متوسط الأجل",
    TradeType.LONG_TERM_INVESTMENT: "استثمار طويل الأجل",
}


class EntryStatus(str, Enum):
    """Section E's entry-status taxonomy. `CONDITIONAL_ON_BREAKOUT` is
    defined for API/forward compatibility but never assigned today --
    it requires a real breakout-pattern detector, explicitly deferred
    to Phase 2F's documented (not-yet-implemented) pattern-detection
    extension point. See `trade_classification.classify_entry_status`'s
    docstring."""

    READY_NOW = "READY_NOW"
    NEAR_ENTRY = "NEAR_ENTRY"
    WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"
    MISSED_ENTRY = "MISSED_ENTRY"
    CONDITIONAL_ON_BREAKOUT = "CONDITIONAL_ON_BREAKOUT"
    NOT_SUITABLE = "NOT_SUITABLE"


ENTRY_STATUS_LABELS_AR = {
    EntryStatus.READY_NOW: "مناسب الآن",
    EntryStatus.NEAR_ENTRY: "قريب من الدخول",
    EntryStatus.WAIT_FOR_PULLBACK: "انتظار التراجع",
    EntryStatus.MISSED_ENTRY: "فاتت نقطة الدخول",
    EntryStatus.CONDITIONAL_ON_BREAKOUT: "دخول مشروط بالاختراق",
    EntryStatus.NOT_SUITABLE: "غير مناسب للدخول",
}

# Arabic labels for src.analysis.decision.types.EntryQuality /
# RiskLevel -- both already computed upstream by AIDecisionEngine;
# these dicts exist only so DecisionResult can carry the Arabic label
# directly (the same "backend supplies label_ar, frontend never
# re-translates" rule DECISION_LABELS_AR already follows), not to
# reclassify either value.
ENTRY_QUALITY_LABELS_AR = {
    "POOR": "ضعيفة",
    "FAIR": "مقبولة",
    "GOOD": "جيدة",
    "EXCELLENT": "ممتازة",
}

RISK_LEVEL_LABELS_AR = {
    "LOW": "منخفضة",
    "MEDIUM": "متوسطة",
    "HIGH": "مرتفعة",
    "VERY_HIGH": "مرتفعة جدًا",
}


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

    # ======================================================================
    # Phase 2A canonical extensions -- every field below is computed from
    # data this engine (or AIDecisionEngine/TechnicalAnalysisEngine
    # upstream of it) already collects; see trade_classification.py,
    # evidence.py, and reasoning.py for exactly how each is derived, and
    # each module's own docstring for what is honestly NOT computable
    # from this platform's daily-bar-only data (e.g. intraday scalp
    # classification, chart-pattern-based breakout entries) rather than
    # fabricated. All have defaults so this remains a purely additive,
    # non-breaking change to a dataclass every existing caller already
    # constructs by keyword.
    # ======================================================================

    # --- A: identity / data status ----------------------------------------
    is_real_data: bool = True
    quote_timestamp: Optional[datetime] = None

    # --- C: confidence breakdown (aliases of sub_scores, not a second
    # scoring system -- see reasoning.py's module docstring) -------------
    technical_confidence: Optional[float] = None
    momentum_confidence: Optional[float] = None
    liquidity_confidence: Optional[float] = None
    market_context_confidence: Optional[float] = None
    data_quality_confidence: Optional[float] = None

    # --- D: trade classification -------------------------------------------
    trade_type: Optional[TradeType] = None
    trade_type_label_ar: str = "غير محدد"
    time_horizon_rationale_ar: str = ""

    # --- E: price plan -------------------------------------------------------
    best_entry_price: Optional[float] = None
    accumulation_zone_low: Optional[float] = None
    accumulation_zone_high: Optional[float] = None
    entry_quality: str = "FAIR"
    entry_quality_label_ar: str = ""
    entry_status: EntryStatus = EntryStatus.NOT_SUITABLE
    entry_status_label_ar: str = ""

    # --- F: risk plan --------------------------------------------------------
    invalidation_price: Optional[float] = None
    risk_level: str = "MEDIUM"
    risk_level_label_ar: str = ""

    # --- G: targets (per-target time estimate; no fabricated per-target
    # probability -- see reasoning.py) ---------------------------------
    estimated_days_target_1: Optional[int] = None
    estimated_days_target_2: Optional[int] = None
    estimated_days_target_3: Optional[int] = None

    # --- H: support and resistance -------------------------------------------
    nearest_support: Optional[float] = None
    major_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    major_resistance: Optional[float] = None
    breakout_level: Optional[float] = None
    breakdown_level: Optional[float] = None
    support_resistance_evidence_ar: str = ""

    # --- I: liquidity and accumulation --------------------------------------
    current_volume: Optional[float] = None
    average_volume: Optional[float] = None
    relative_volume: Optional[float] = None
    liquidity_quality_ar: str = "غير محدد"
    accumulation_score: Optional[float] = None
    accumulation_assessment_ar: str = ""
    volume_confirms_decision: Optional[bool] = None
    abnormal_volume: bool = False

    # --- J: technical evidence -----------------------------------------------
    technical_evidence: Dict[str, Any] = field(default_factory=dict)
    trend_direction_ar: str = "غير محدد"
    trend_strength_label_ar: str = "غير محدد"

    # --- K: decision reasoning ------------------------------------------------
    decision_summary_ar: str = ""
    why_now_ar: str = ""
    why_not_stronger_ar: str = ""
    entry_confirmation_conditions_ar: List[str] = field(default_factory=list)
    watch_next_session_ar: List[str] = field(default_factory=list)
