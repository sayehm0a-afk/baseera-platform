"""Request/response schemas for /api/v1/market/* -- follows the same
conventions as src/api/schemas/backtesting.py and stocks.py.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MarketScanRequest(BaseModel):
    symbols: Optional[List[str]] = Field(
        default=None,
        description="Explicit symbols to scan; omit to scan every active, price-history-eligible symbol.",
    )


class MarketScanRunOut(BaseModel):
    id: int
    status: str
    symbols_requested: int
    symbols_succeeded: int
    symbols_skipped: int
    symbols_failed: int
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    created_at: datetime


class MarketScanProgressOut(BaseModel):
    """Live progress for one MarketScanRun, read from MarketScanProgress
    (src.market_intelligence.scan_progress.ScanProgressTracker writes
    this row after every symbol). Returns 404 (via NoMarketScanDataError)
    if no progress row exists yet for the run -- e.g. a run dispatched
    by a code path that doesn't use a ScanProgressTracker."""

    run_id: int
    status: str
    eligible_discovered: int
    completed_count: int
    remaining_count: int
    progress_pct: float
    success_count: int
    failed_count: int
    skipped_count: int
    insufficient_data_count: int
    published_count: int
    rejected_count: int
    watch_only_count: int
    not_evaluated_count: int
    current_symbol: Optional[str] = None
    current_symbol_name_en: Optional[str] = None
    current_symbol_name_ar: Optional[str] = None
    last_completed_symbol: Optional[str] = None
    api_calls_total: int
    retries_total: int
    latest_error: Optional[str] = None
    latest_warning: Optional[str] = None
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RankingEntryOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    final_score: Optional[float] = None
    target_price: Optional[float] = None
    expected_return_pct: Optional[float] = None
    risk_level: Optional[str] = None
    rank_value: Optional[float] = None
    current_price: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    time_horizon: Optional[str] = None


class RankingListOut(BaseModel):
    category: str
    entries: List[RankingEntryOut]
    generated_at: datetime


class RankingsOut(BaseModel):
    scan_run_id: Optional[int] = None
    rankings: List[RankingListOut]


class OpportunityCategoryOut(BaseModel):
    """Phase 2D (Stock Ranking Engine): one of the 8 curated
    Product-Owner-facing opportunity categories -- see
    src.market_intelligence.opportunity_ranking. `label_ar` and
    `scoring_factor_ar` make the ranking's real sort field explicit
    rather than leaving the frontend to guess from a bare category
    enum value."""

    category: str
    label_ar: str
    scoring_factor_ar: str
    gate_exclusion_note_ar: str
    entries: List[RankingEntryOut]
    generated_at: datetime


class OpportunitiesOut(BaseModel):
    scan_run_id: Optional[int] = None
    categories: List[OpportunityCategoryOut]


class WatchlistEntryOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    reason: str


class WatchlistResultOut(BaseModel):
    category: str
    entries: List[WatchlistEntryOut]
    generated_at: datetime


class WatchlistsOut(BaseModel):
    scan_run_id: Optional[int] = None
    watchlists: List[WatchlistResultOut]


class SectorSummaryOut(BaseModel):
    sector: str
    symbol_count: int
    average_confidence: Optional[float] = None
    average_final_score: Optional[float] = None
    average_expected_return_pct: Optional[float] = None
    average_technical_score: Optional[float] = None
    average_fundamental_score: Optional[float] = None
    buy_count: int
    sell_count: int
    hold_count: int
    breadth: float
    momentum: Optional[float] = None


class SectorsOut(BaseModel):
    scan_run_id: Optional[int] = None
    sectors: List[SectorSummaryOut]


class ChangeEventOut(BaseModel):
    symbol: str
    change_type: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    delta: Optional[float] = None
    detected_at: datetime


class ChangesOut(BaseModel):
    total: int
    limit: int
    offset: int
    changes: List[ChangeEventOut]


class AlertOut(BaseModel):
    alert_type: str
    severity: str
    symbol: Optional[str] = None
    sector: Optional[str] = None
    message: str
    generated_at: datetime


class AlertsOut(BaseModel):
    total: int
    limit: int
    offset: int
    alerts: List[AlertOut]


class DiagnosticSampleSymbolOut(BaseModel):
    symbol: str
    recommendation: str
    latest_price: Optional[float] = None
    evaluated_at: datetime


class DiagnosticDecisionV2SampleOut(BaseModel):
    """Phase 3A evidence: one DecisionV2Snapshot row this diagnostic
    scan itself just wrote -- proves the scheduled-scan pipeline (not
    just the on-demand /decision-v2 route) now computes and persists a
    real Decision Engine V2 result with `scan_run_id` populated."""

    symbol: str
    decision: str
    decision_label_ar: str
    confidence_score: float
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    scan_run_id: Optional[int] = None
    decision_timestamp: datetime


class DiagnosticScanOut(BaseModel):
    """Response for POST /api/v1/admin/market-intelligence/diagnostic-scan
    -- real evidence from one controlled SAHMK poll, never fabricated:
    every field below is either read from provider_factory's real
    connectivity-probe state or from rows the scan itself just wrote."""

    triggered_at: datetime
    operation_tested: str
    sahmk_connectivity_status: str
    sahmk_error: Optional[str] = None
    current_provider_kind: Optional[str] = None
    last_connectivity_status: Optional[str] = None
    last_connectivity_at: Optional[str] = None
    can_publish_recommendations: bool
    strict_real_data: bool
    synthetic_allowed: bool
    sahmk_key_present: bool
    run_id: Optional[int] = None
    run_status: Optional[str] = None
    run_error_summary: Optional[str] = None
    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    rows_written: int = 0
    sample_symbols: List[DiagnosticSampleSymbolOut] = Field(default_factory=list)
    last_scan_source: Optional[str] = None
    data_is_fresh: Optional[bool] = None
    freshness_note: str = ""
    decision_v2_rows_written: int = 0
    decision_v2_sample: List[DiagnosticDecisionV2SampleOut] = Field(default_factory=list)
    latest_completed_run_id: Optional[int] = None
    latest_completed_run_v1_rows_written: int = 0
    latest_completed_run_v1_sample_symbols: List[DiagnosticSampleSymbolOut] = Field(default_factory=list)
    latest_completed_run_decision_v2_rows_written: int = 0
    latest_completed_run_decision_v2_sample: List[DiagnosticDecisionV2SampleOut] = Field(default_factory=list)


class MarketStatusOut(BaseModel):
    """GET /api/v1/market/status -- Tadawul session state for the
    frontend's status banner (src.market_intelligence.market_status).
    `status` is one of OPEN/PRE_MARKET/PRE_OPEN_AUCTION/CLOSING_AUCTION/
    CLOSING_PRICE_TRADING/POST_CLOSE/WEEKEND/CLOSED/UNKNOWN/
    PROVIDER_UNREACHABLE (see MarketSessionStatus; the last one
    overrides the calendar-derived value whenever the configured
    market data provider's own health check fails, regardless of what
    the calendar says)."""

    status: str
    label_ar: str
    is_trading_day: bool
    server_time_riyadh: datetime
    seconds_until_next_open: float
    seconds_until_close: Optional[float] = None
    last_completed_session_date: Optional[str] = None
    provider_connected: bool
    holiday_calendar_disclosed_gap: str


class UniverseBucketCountOut(BaseModel):
    """One row of Stock.instrument_bucket -> count -- e.g. how many
    discovered instruments are common equities vs. ETFs/REITs/sukuk/
    rights/suspended. `bucket=None` means the row predates universe
    classification (added explicitly, or ingested before this column
    existed), not an unclassified equity."""

    bucket: Optional[str] = None
    count: int


class IngestionJobStatusOut(BaseModel):
    """The most recent IngestionRunLog row for one scheduled ingestion
    job (symbols/historical_ohlcv/fundamentals/dividends).
    `status=None` means this job has never run in this deployment."""

    job_name: str
    status: Optional[str] = None
    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    rows_upserted: int = 0
    retry_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_summary: Optional[str] = None


class SectorCoverageOut(BaseModel):
    """One Saudi sector's coverage: how many Stock rows carry this
    sector value, how many of those are eligible/active, and how many
    of the active ones actually have price history to scan. `sector`
    is the raw value stored on Stock.sector (SAHMK-reported); `None`
    means the sector field is unresolved for those rows (a disclosed
    SAHMK data-source gap, not an ingestion bug -- see
    universe_policy.py's module docstring)."""

    sector: Optional[str] = None
    total_stocks: int
    active_stocks: int
    stocks_with_price_history: int
    coverage_pct: Optional[float] = None


class DbConsistencyOut(BaseModel):
    """Direct counts of Stock rows whose stored fields are internally
    inconsistent -- e.g. an active stock with no instrument_bucket
    recorded, or an inactive stock with no exclusion_reason recorded.
    All zero means every discovered symbol's eligibility/classification
    state is fully and consistently persisted."""

    active_stocks_missing_instrument_bucket: int
    active_stocks_missing_sector: int
    active_stocks_missing_exchange: int
    inactive_stocks_missing_exclusion_reason: int
    active_stocks_with_exclusion_reason_set: int


class PipelineStageOut(BaseModel):
    """One stage of the Discovery -> OHLCV -> Fundamentals ->
    Dividends -> Decision Engine -> Recommendation Engine pipeline,
    measured against the total discovered-symbol count. `dropped` is
    `relative_to - output`, not necessarily a sequential filter --
    each stage's real gating condition is documented in `reason`."""

    stage: str
    output_count: int
    relative_to: int
    dropped: int
    reason: str


class DecisionCountOut(BaseModel):
    """One Decision Engine V2 value (e.g. BUY_CANDIDATE) -> how many
    symbols' latest decision, within the reporting window, was that
    value."""

    decision: str
    count: int


class ConfidenceBucketCountOut(BaseModel):
    """One 20-point confidence-score bucket ("0-20", ..., "80-100") ->
    how many symbols' latest decision fell in it."""

    bucket_label: str
    count: int


class RiskCountOut(BaseModel):
    risk_level: Optional[str] = None
    count: int


class TopOpportunityOut(BaseModel):
    """One of the current highest-confidence BUY_CANDIDATE/
    STRONG_BUY_CANDIDATE symbols, most recent decision only."""

    symbol: str
    company_name_ar: Optional[str] = None
    sector_ar: Optional[str] = None
    decision: str
    decision_label_ar: str
    confidence_score: float
    risk_level: Optional[str] = None
    decision_timestamp: datetime


class RejectedOpportunityOut(BaseModel):
    """One of the most recent REJECT/INSUFFICIENT_DATA symbols, with the
    real blocking-gate names that caused it -- never a guess."""

    symbol: str
    company_name_ar: Optional[str] = None
    sector_ar: Optional[str] = None
    decision: str
    failed_gate_names: List[str]
    decision_timestamp: datetime


class RejectionReasonCountOut(BaseModel):
    """How many of the window's REJECT/INSUFFICIENT_DATA/WAIT_FOR_ENTRY
    symbols failed each named gate -- a real tally over `gates` JSON,
    not a category label."""

    gate_name: str
    fail_count: int


class SectorRankingOut(BaseModel):
    sector_ar: Optional[str] = None
    symbols_evaluated: int
    average_confidence: Optional[float] = None
    buy_candidate_count: int


class DecisionIntelligenceOut(BaseModel):
    """GET /api/v1/admin/market-intelligence/decision-intelligence --
    real SQL-backed statistics over each symbol's most recent Decision
    Engine V2 snapshot within the reporting window: decision/confidence/
    risk distribution, top opportunities, rejected opportunities with
    their real gate-failure reasons, and sector ranking. Every number is
    a direct aggregate over decision_v2_snapshots, never estimated."""

    generated_at: datetime
    window_hours: int
    total_symbols_evaluated: int
    decision_distribution: List[DecisionCountOut]
    confidence_buckets: List[ConfidenceBucketCountOut]
    risk_distribution: List[RiskCountOut]
    top_opportunities: List[TopOpportunityOut]
    rejected_opportunities: List[RejectedOpportunityOut]
    rejection_reason_counts: List[RejectionReasonCountOut]
    sector_ranking: List[SectorRankingOut]


class MarketCoverageOut(BaseModel):
    """GET /api/v1/admin/market-intelligence/coverage -- real,
    SQL-backed evidence of how much of the Saudi market Basirah
    actually tracks, scans, and can recommend from, right now. Every
    field is a direct query result, never estimated."""

    generated_at: datetime
    total_stocks: int
    active_stocks: int
    inactive_stocks: int
    stocks_with_price_history: int
    stocks_without_price_history: int
    instrument_bucket_counts: List[UniverseBucketCountOut]
    ingestion_auto_discover_enabled: bool
    ingestion_configured_seed_symbols: int
    latest_ingestion_runs: List[IngestionJobStatusOut]
    latest_scan_run: Optional[MarketScanRunOut] = None
    coverage_pct: Optional[float] = None

    # Main Market vs Nomu split, derived from instrument_bucket prefix
    # (MAIN_MARKET_EQUITY*/NOMU_EQUITY*) -- universe_policy.classify_universe
    # already distinguishes these; unclassified_market_segment_stocks
    # covers rows whose bucket doesn't positively match either segment
    # (never-classified rows, or a non-equity bucket).
    main_market_stocks: int
    nomu_market_stocks: int
    unclassified_market_segment_stocks: int

    # Non-equity exclusion breakdown -- the subset of
    # instrument_bucket_counts whose bucket is a confirmed exclusion
    # reason (ETF_FUND/REIT/SUKUK_BOND/RIGHTS_ISSUE/SUSPENDED/
    # INACTIVE_DELISTED), plus the total excluded for a quick top-line
    # number.
    excluded_instrument_counts: List[UniverseBucketCountOut]
    total_excluded_non_equity: int

    stocks_with_fundamentals: int
    stocks_without_fundamentals: int
    stocks_with_dividends: int
    stocks_without_dividends: int

    sector_coverage: List[SectorCoverageOut]

    latest_scan_symbols_entering_decision_engine: int
    latest_scan_recommendations_generated: int

    db_consistency: DbConsistencyOut
    pipeline_funnel: List[PipelineStageOut]


class MarketSummaryOut(BaseModel):
    scan_run_id: Optional[int] = None
    generated_at: datetime
    symbols_scanned: int
    bull_bear_ratio: Optional[float] = None
    average_confidence: Optional[float] = None
    average_recommendation_score: Optional[float] = None
    buy_signal_count: int
    sell_signal_count: int
    strongest_sectors: List[str]
    weakest_sectors: List[str]
    most_important_changes: List[ChangeEventOut]
