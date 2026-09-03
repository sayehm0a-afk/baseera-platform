"""Versioned, strictly-typed I/O contract for the Basirah Brain Stage 1
AI-analyst synthesis layer.

Every field on `BasirahBrainInputV1` is either real, already-computed
evidence from Basirah's existing deterministic pipeline
(`src.analysis.decision_v2`), or an explicit `None`/empty-list when that
evidence genuinely does not exist yet (e.g. weekly-timeframe data,
sector relative strength, an earnings calendar) -- see the prior
architecture audit's Phase 3/13 gap list. Nothing here is fabricated to
fill out the schema; a missing field is a signal to the Brain, not a
placeholder to hide.

`BasirahBrainDecisionV1` is the Brain's own, machine-readable output --
never free-form prose as the authoritative decision. `confidence_score`
is explicitly NOT a probability of success (see `confidence_label`'s
docstring and CONFIDENCE_MEANING below) -- Basirah has not proven a
calibrated hit rate, and this schema must not imply one.
"""

import enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1"

# Explicit, disclosed meaning of confidence_score -- reused verbatim by
# prompts.py's system prompt and by the API layer whenever this field is
# surfaced, so the "not a probability" disclosure can never silently
# drift out of sync between the model instructions and any future
# display surface.
CONFIDENCE_MEANING = (
    "confidence_score measures the strength and internal consistency of the supplied evidence, "
    "not a statistically calibrated probability of trade success. Basirah has not yet proven a "
    "calibrated real-world hit rate for any confidence band."
)


class BrainDecision(str, enum.Enum):
    BUY = "BUY"
    WAIT_FOR_ENTRY = "WAIT_FOR_ENTRY"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"


class ConfidenceLabel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BrainRiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AgreementStatus(str, enum.Enum):
    AGREE = "AGREE"
    DISAGREE = "DISAGREE"
    MORE_CONSERVATIVE = "MORE_CONSERVATIVE"


# ===========================================================================
# INPUT SCHEMA -- BasirahBrainInputV1
# ===========================================================================


class BrainIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    timestamp: str  # ISO-8601, the moment this evidence package was assembled
    market_session_status: str  # e.g. "OPEN" / "CLOSED" / "PRE_MARKET" -- as reported by the existing engine


class BrainOhlcvBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class BrainPriceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    price_change_pct: Optional[float] = None
    recent_daily_bars: List[BrainOhlcvBar] = Field(default_factory=list)
    # NEW capability gap (architecture audit G7): Basirah currently
    # ingests daily bars only -- no weekly timeframe exists anywhere in
    # the codebase. Always None today; kept as a real field so a future
    # PR can populate it without a schema break, and so the Brain is
    # told explicitly that no weekly confirmation is available rather
    # than silently missing it.
    recent_weekly_bars: Optional[List[BrainOhlcvBar]] = None
    data_freshness_status: str = "UNKNOWN"  # DataFreshnessStatus.value from the deterministic engine
    quote_timestamp: Optional[str] = None


class BrainTechnicalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend_state: Optional[str] = None
    trend_score: Optional[float] = None
    momentum_score: Optional[float] = None
    volatility_score: Optional[float] = None
    atr_pct: Optional[float] = None
    support_levels: List[float] = Field(default_factory=list)
    resistance_levels: List[float] = Field(default_factory=list)
    current_volume: Optional[float] = None
    average_volume: Optional[float] = None
    relative_volume: Optional[float] = None
    liquidity_quality: Optional[str] = None
    breakout_status: Optional[str] = None
    entry_quality: Optional[str] = None
    anti_chase_state: Optional[str] = None  # entry_status when it reflects a chase/missed-entry condition


class BrainMarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_regime_state: Optional[str] = None
    market_regime_basis: Optional[str] = None
    market_regime_entry_permitted: Optional[bool] = None
    # NEW capability gaps (architecture audit): no independent TASI/index
    # feed and the sector relative-strength contributor is a dead stub
    # today -- always None until a real feed is wired in. See
    # evidence_builder.py for why these are never fabricated.
    index_direction: Optional[str] = None
    index_strength: Optional[float] = None
    sector_performance: Optional[str] = None
    relative_strength_vs_sector: Optional[float] = None


class BrainFundamentals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valuation_summary: Optional[str] = None
    growth_summary: Optional[str] = None
    profitability_summary: Optional[str] = None
    balance_sheet_summary: Optional[str] = None
    fundamental_score: Optional[float] = None
    missing_data_flags: List[str] = Field(default_factory=list)


class BrainNewsHeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    published_at: Optional[str] = None
    sentiment_label: Optional[str] = None
    source: Optional[str] = None


class BrainNewsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recent_headlines: List[BrainNewsHeadline] = Field(default_factory=list)
    aggregate_sentiment_score: Optional[float] = None
    # The existing engine's own discrete news-impact classification
    # (news_impact / news_impact_summary_ar on DecisionResult) -- real,
    # DB-only evidence already computed upstream, distinct from a raw
    # numeric sentiment score which is not exposed at this layer.
    impact_label: Optional[str] = None
    impact_summary: Optional[str] = None
    article_count: int = 0
    missing_data_flags: List[str] = Field(default_factory=list)


class BrainEventRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # NEW capability gap (architecture audit G6): no earnings-calendar
    # ingestion exists anywhere in the codebase -- always None today.
    next_earnings_date: Optional[str] = None
    days_to_earnings: Optional[int] = None
    known_corporate_action: Optional[str] = None


class BrainGateOutcomeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    detail: str
    blocking: bool


class BrainExistingEngineEvidence(BaseModel):
    """Verbatim summary of what the existing, unmodified deterministic
    engine (DecisionEngineV2) already concluded -- the Brain's evidence
    baseline, never recomputed here."""

    model_config = ConfigDict(extra="forbid")

    deterministic_decision: str
    deterministic_confidence_score: float
    opportunity_quality_score: Optional[float] = None
    risk_score: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    holding_horizon_min_days: Optional[int] = None
    holding_horizon_max_days: Optional[int] = None
    risk_reward_target_1: Optional[float] = None
    sub_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    gate_outcomes: List[BrainGateOutcomeEvidence] = Field(default_factory=list)
    rejection_or_watch_reasons: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)


class BrainDataQualityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stale_flags: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    is_synthetic: bool = False
    provider_status: Optional[str] = None


class BasirahBrainInputV1(BaseModel):
    """Versioned structured-evidence package handed to a
    `BasirahBrainProvider`. Never mutated after construction (the
    provider only reads it); `service.py` hashes its canonical JSON form
    for reproducibility/audit."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    identity: BrainIdentity
    price_context: BrainPriceContext
    technical: BrainTechnicalEvidence
    market_context: BrainMarketContext
    fundamentals: BrainFundamentals
    news: BrainNewsEvidence
    event_risk: BrainEventRisk
    existing_engine: BrainExistingEngineEvidence
    data_quality: BrainDataQualityIn


# ===========================================================================
# OUTPUT SCHEMA -- BasirahBrainDecisionV1
# ===========================================================================


class BrainEntryZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: Optional[float] = None
    high: Optional[float] = None

    @model_validator(mode="after")
    def _low_le_high(self) -> "BrainEntryZone":
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("entry_zone.low must be <= entry_zone.high")
        return self


class BrainHoldingHorizon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_days: Optional[int] = None
    max_days: Optional[int] = None

    @model_validator(mode="after")
    def _min_le_max(self) -> "BrainHoldingHorizon":
        if self.min_days is not None and self.max_days is not None and self.min_days > self.max_days:
            raise ValueError("holding_horizon.min_days must be <= max_days")
        return self


class BrainKeyEvidence(BaseModel):
    """Mandatory evidence-traceability item: every material claim must
    cite the exact input field it came from -- see module docstring."""

    model_config = ConfigDict(extra="forbid")

    category: str
    statement: str
    source_field: str


class BrainDataQualityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    missing_critical_fields: List[str] = Field(default_factory=list)
    stale_inputs: List[str] = Field(default_factory=list)


class BasirahBrainDecisionV1(BaseModel):
    """Strict, machine-readable Brain output. Post-generation validators
    (validators.py) may correct `decision`/`entry_zone`/`stop_loss`/
    `targets` after this model is first parsed (hard-gate policy,
    price-level normalization) -- this class only enforces internal
    structural validity, not Basirah's safety policy, which is layered
    on top by validators.py/service.py."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION

    decision: BrainDecision
    confidence_score: float = Field(ge=0, le=100)
    confidence_label: ConfidenceLabel

    entry_zone: BrainEntryZone = Field(default_factory=BrainEntryZone)
    stop_loss: Optional[float] = None
    targets: List[float] = Field(default_factory=list)

    holding_horizon: BrainHoldingHorizon = Field(default_factory=BrainHoldingHorizon)
    risk_level: BrainRiskLevel

    thesis_summary: str
    bull_case: List[str] = Field(default_factory=list)
    bear_case: List[str] = Field(default_factory=list)
    key_evidence: List[BrainKeyEvidence] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)
    monitoring_conditions: List[str] = Field(default_factory=list)

    data_quality: BrainDataQualityOut

    agreement_with_deterministic_engine: AgreementStatus
    deterministic_decision: str
    brain_decision: str

    reason_codes: List[str] = Field(default_factory=list)

    @field_validator("confidence_score")
    @classmethod
    def _finite(cls, v: float) -> float:
        # Pydantic's float coercion already accepts NaN/inf from a
        # permissive JSON parse -- reject them explicitly rather than
        # relying on ge/le alone (NaN compares False to both bounds and
        # would otherwise slip through Field(ge=0, le=100) silently).
        import math

        if not math.isfinite(v):
            raise ValueError("confidence_score must be a finite number")
        return v

    @field_validator("targets")
    @classmethod
    def _targets_finite_and_ordered(cls, v: List[float]) -> List[float]:
        import math

        for t in v:
            if not math.isfinite(t):
                raise ValueError("targets must be finite numbers")
        if v != sorted(v):
            raise ValueError("targets must be in non-decreasing order (target_1 <= target_2 <= target_3)")
        return v
