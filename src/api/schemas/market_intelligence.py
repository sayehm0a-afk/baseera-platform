"""Request/response schemas for /api/v1/market/* -- follows the same
conventions as src/api/schemas/backtesting.py and stocks.py.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from src.domain.sector_labels import sector_label_ar


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
    skipped_symbols_summary: Optional[str] = None
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
    sector_ar: Optional[str] = None
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


class PersonalOpportunityOut(BaseModel):
    """One card for the personal "أفضل فرص المضاربة الآن" screen --
    every field is read straight from a persisted `DecisionV2Snapshot`
    row (see src.market_intelligence.personal_scan), never recomputed
    or fabricated for this view. `simple_decision_ar` collapses the
    full Decision taxonomy to the three-word action the mandate's
    primary UI requires (شراء / انتظار / تجاهل); `decision_label_ar`
    keeps the fuller existing label (e.g. "شراء قوي") for anyone who
    wants the extra nuance."""

    rank: int
    symbol: str
    company_name_ar: Optional[str] = None
    company_name_en: str
    sector_ar: Optional[str] = None

    decision: str
    decision_label_ar: str
    simple_decision_ar: str

    current_price: Optional[float] = None
    market_status: str
    market_status_label_ar: str

    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    entry_status_label_ar: Optional[str] = None
    is_entry_late: bool

    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward_target_1: Optional[float] = None

    confidence_score: float
    risk_level_label_ar: Optional[str] = None

    decision_summary_ar: Optional[str] = None
    entry_confirmation_conditions_ar: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)

    expected_holding_period_label_ar: Optional[str] = None
    trend_direction_ar: Optional[str] = None
    trend_strength_label_ar: Optional[str] = None
    liquidity_quality_ar: Optional[str] = None

    nearest_resistance: Optional[float] = None
    breakout_level: Optional[float] = None

    decision_timestamp: datetime


class PersonalScanOut(BaseModel):
    """GET /api/v1/market/personal/top-opportunities -- at most 5
    unique symbols, or an explicit empty state with `message_ar` set to
    one of the two honest Arabic states the mandate specifies: no
    sufficiently strong opportunity right now (`is_stale=False`, real
    fresh data was checked and nothing qualified), or the data itself
    is too old to issue a new recommendation from (`is_stale=True`)."""

    scan_run_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    data_age_hours: Optional[float] = None
    max_data_age_hours: float
    is_stale: bool
    # CONT Phase 6: a 4-state honest freshness read (FRESH/AGING/STALE/
    # NO_SCAN, see personal_scan.py) so the frontend can show "getting
    # old but still usable" distinctly from a hard staleness cutoff,
    # instead of only the coarser `is_stale` boolean. `freshness_label_ar`
    # is the ready-to-render Arabic text -- the frontend never needs to
    # translate `freshness_state` itself.
    freshness_state: str
    freshness_label_ar: str
    opportunities: List[PersonalOpportunityOut]
    message_ar: Optional[str] = None


class WatchlistEntryOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    sector_ar: Optional[str] = None
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
    sector_ar: Optional[str] = None
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

    @model_validator(mode="after")
    def _fill_sector_ar(self) -> "SectorSummaryOut":
        if self.sector_ar is None:
            self.sector_ar = sector_label_ar(self.sector)
        return self


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


class ObservedFieldValueOut(BaseModel):
    """One distinct literal value SAHMK's /companies/ directory actually
    returned for a given field (market/market_segment/security_type/
    status/is_etf), and how many instruments carried it -- the real
    evidence universe_policy.classify_universe's marker lists are
    checked against, surfaced instead of silently discarded."""

    value: str
    count: int


class ObservedFieldOut(BaseModel):
    field: str
    distinct_values: List[ObservedFieldValueOut]


class UniverseSampleEntryOut(BaseModel):
    """One raw /companies/ directory entry's real classification-relevant
    fields, for a human to eyeball against `observed_fields` -- e.g.
    confirming a specific symbol/name is a known Nomu-listed company
    lines up with a specific market_segment literal."""

    symbol: str
    name_en: Optional[str] = None
    market: Optional[str] = None
    market_segment: Optional[str] = None
    security_type: Optional[str] = None
    status: Optional[str] = None
    bucket: str


class DirectoryPaginationDiagnosticsOut(BaseModel):
    """Real evidence from SahmkMarketDataService.last_directory_
    diagnostics -- answers, from the actual raw /companies/ response
    envelope, whether the ~100-instrument result is a pagination limit
    (a `next`/`count`/`total` signal was present but not fully
    followed/reconciled), a fully-verified complete universe (a
    reported total existed and was fully reconciled), or a response
    that never carried any pagination signal at all (in which case a
    single call's result-set size is not provable as a page limit from
    the response shape alone -- it is either the true full universe or
    a silent, unsignaled cap, and this field cannot by itself
    distinguish those two)."""

    pages_fetched: int = 0
    total_fetched: int = 0
    pagination_signal: Optional[str] = None
    reported_total: Optional[int] = None
    universe_verdict: str = "NOT_YET_RUN"
    first_page_keys: List[str] = Field(default_factory=list)
    first_item_keys: List[str] = Field(default_factory=list)
    sector_populated_count: int = 0
    name_ar_populated_count: int = 0


class UniverseDiagnosticsOut(BaseModel):
    """Response for GET /api/v1/admin/market-intelligence/
    universe-diagnostics -- a fresh, live SAHMK /companies/ directory
    call (cached 24h, so cheap to repeat) run through
    universe_policy.classify_universe, with its full per-field
    distinct-value breakdown surfaced. Exists to answer, with real
    evidence rather than a guess, whether SAHMK's real market_segment
    (or another field) values for Nomu-listed instruments are simply
    not among the substrings universe_policy currently matches, and
    (via `pagination`) whether the ~100-instrument total is a
    pagination artifact or the provider's genuine result set."""

    generated_at: datetime
    provider_kind: Optional[str] = None
    sahmk_error: Optional[str] = None
    total_instruments: int = 0
    bucket_counts: Dict[str, int] = Field(default_factory=dict)
    observed_fields: List[ObservedFieldOut] = Field(default_factory=list)
    sample_entries: List[UniverseSampleEntryOut] = Field(default_factory=list)
    pagination: Optional[DirectoryPaginationDiagnosticsOut] = None


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
    zero_progress_summary: Optional[str] = None
    # Only ever set when status="deferred" -- the pipeline correctly
    # holding this job back because SAHMK's own quota governor refused
    # a background-priority request to protect the reserve for
    # live-market-critical operations, not a genuine ingestion defect.
    # When to expect it to resume automatically.
    next_retry_at: Optional[datetime] = None


class FullDiscoveryTriggerOut(BaseModel):
    """POST /api/v1/admin/market-intelligence/full-discovery -- ack for
    a staff-triggered manual run of the same four ingestion jobs
    (symbols -> historical_ohlcv -> fundamentals -> dividends) the
    recurring scheduler would eventually run, dispatched as a
    background task since a full-market backfill can take many
    minutes. `accepted=False` means an equivalent run was already in
    progress and this call was a no-op -- poll GET /coverage's
    latest_ingestion_runs for real before/after counts."""

    triggered_at: datetime
    accepted: bool
    message: str
    job_names: List[str] = Field(default_factory=list)


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
    decision_label_ar: str
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
    decision_label_ar: str
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
    # Distinguishes "no authoritative sector-classification source has
    # ever been configured" (False -- the current, honest production
    # state; SAHMK's /companies/ directory has no sector field for most
    # symbols and no other legitimate source is wired up) from "a real
    # source is configured but this particular symbol still has no
    # sector" (True). See src.market_data.providers.sector_provider.
    sector_provider_configured: bool = False

    latest_scan_symbols_entering_decision_engine: int
    latest_scan_recommendations_generated: int

    db_consistency: DbConsistencyOut
    pipeline_funnel: List[PipelineStageOut]

    # Exact symbol identity, not just an aggregate count -- a real
    # production gap found while root-causing why 408/408 OHLCV-sync
    # "succeeded" but only 393 stocks actually carry PriceBar rows: the
    # aggregate count alone gave no way to find which 15 symbols or why.
    # Capped so a badly-degraded universe can't return an unbounded list.
    symbols_missing_price_history: List[str] = []

    # Retroactive diff-based reconstruction for the latest scan: active,
    # price-history-eligible symbols with no SymbolIntelligenceRecord
    # tied to latest_scan_run.id. Exact only if the universe hasn't
    # changed since that scan ran (true whenever no ingestion has run
    # since); a scan_run created after skipped_symbols_summary (see
    # MarketScanRun) exists is reported from that column directly
    # instead, since it's the real per-symbol reason, not a diff guess.
    latest_scan_skipped_symbols: List[str] = []


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


class SymbolLookupCheckOut(BaseModel):
    """One real SAHMK API call's real outcome for a single symbol --
    never a guess. `available` is only ever True when the call actually
    returned usable data; any exception (including a clean 404/'not
    found' business response) is captured verbatim in `detail` and
    `available` stays False."""

    available: bool
    detail: Optional[str] = None
    raw_sector: Optional[str] = None
    raw_industry: Optional[str] = None
    raw_keys: Optional[List[str]] = None


class SymbolLookupDiagnosticOut(BaseModel):
    """Real per-symbol evidence for whether SAHMK's directory-discovery
    cap (see UniverseDiagnosticsOut.pagination) is a DISCOVERY-only
    limitation or a genuine DATA-coverage limitation: for a symbol that
    is NOT among the ~100 instruments the /companies/ directory
    returns, does SAHMK's per-symbol quote/profile/historical/
    fundamentals/dividends endpoints still serve real data when called
    directly by symbol? If yes, the fix is symbol-discovery (e.g. a
    static/official symbol seed list feeding the existing per-symbol
    endpoints), not a data-provider replacement."""

    symbol: str
    in_last_known_directory: Optional[bool] = None
    quote: SymbolLookupCheckOut
    company_profile: SymbolLookupCheckOut
    historical_bar: SymbolLookupCheckOut
    dividends: SymbolLookupCheckOut
    dividends_raw: Optional[SymbolLookupCheckOut] = None
    fundamentals: SymbolLookupCheckOut


class SymbolLookupDiagnosticsOut(BaseModel):
    generated_at: datetime
    provider_kind: Optional[str] = None
    sahmk_error: Optional[str] = None
    results: List[SymbolLookupDiagnosticOut] = Field(default_factory=list)


class ContinueScanCycleOut(BaseModel):
    """Response for POST /api/v1/admin/market-intelligence/continue-scan-cycle
    -- one manually-advanced cycle of the exact same bounded, stale-first,
    BACKGROUND-priority, leader-locked rotation
    IntervalMarketIntelligenceScheduler._run_one_cycle() runs on its own
    (daily) interval. `executed=False` always means no scan ran and no
    SAHMK quota was spent this call -- `stop_reason` says why (a genuine
    safety gate, universe fully covered, or a concurrency skip)."""

    triggered_at: datetime
    executed: bool
    stop_reason: Optional[str] = None
    in_flight_run_id: Optional[int] = None

    run_id: Optional[int] = None
    run_status: Optional[str] = None
    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_skipped: int = 0
    symbols_failed: int = 0
    skipped_symbols_summary: Optional[str] = None
    symbols_scanned: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    quota_before: Optional[Dict] = None
    quota_after: Optional[Dict] = None
    cache_status_before: Optional[Dict] = None
    cache_status_after: Optional[Dict] = None

    recommendation_counts: Dict[str, int] = Field(default_factory=dict)
    decision_counts: Dict[str, int] = Field(default_factory=dict)
    published_count: int = 0
    rejected_count: int = 0
    watch_only_count: int = 0


class Stage1SignalOut(BaseModel):
    name: str
    detail_ar: str


class Stage1ComponentScoresOut(BaseModel):
    """The six sub-scores (0-100, 50=neutral) behind `ranking_score` --
    trend/momentum/volume/liquidity/volatility/risk_reward, exactly as
    `src.analysis.decision_v2.scoring.opportunity_quality_score` combines
    them for the live decision pipeline. `None` means genuinely not
    computable for this symbol (excluded from the weighted blend, not
    defaulted to a number) -- this is what lets a caller see WHY a
    candidate ranked where it did, not just the final score."""

    trend: Optional[float] = None
    momentum: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    volatility: Optional[float] = None
    risk_reward: Optional[float] = None


class Stage1CandidateOut(BaseModel):
    symbol: str
    latest_close: Optional[float] = None
    latest_bar_timestamp: Optional[datetime] = None
    dollar_volume: Optional[float] = None
    relative_volume: Optional[float] = None
    adx_14: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_pct: Optional[float] = None
    signals: List[Stage1SignalOut] = Field(default_factory=list)
    ranking_score: Optional[float] = None
    component_scores: Stage1ComponentScoresOut = Field(default_factory=Stage1ComponentScoresOut)
    risk_reward_ratio: Optional[float] = None


class Stage1ScanOut(BaseModel):
    """GET /api/v1/admin/market-intelligence/stage1-scan -- Stage 1 of
    the two-stage Radar scan (SAHMK quota optimization mandate,
    2026-08-16). Narrows the full eligible universe to genuine
    candidates using ONLY already-persisted local data -- zero SAHMK
    requests, regardless of universe size. A GET, not a POST: this
    route makes no live provider call and writes nothing, so it is
    safe to call as often as needed."""

    generated_at: datetime
    universe_size: int
    evaluated_count: int
    skipped_count: int
    candidate_count: int
    candidates: List[Stage1CandidateOut] = Field(default_factory=list)


class Stage2ValidateRequest(BaseModel):
    """Request body for POST .../stage2-validate-candidates -- the
    caller supplies the exact symbols Stage 1 (GET .../stage1-scan)
    already narrowed the universe down to. Capped at
    MARKET_SCAN_SYMBOLS_PER_CYCLE per call, same as every other
    manually triggered cycle; call again with the remaining slice for
    a candidate list larger than one cycle."""

    symbols: List[str]


# ============================================================================
# Basirah Radar V2 (2026-08-16) -- Phase D REST API
# ============================================================================


class RadarStage1ComponentScoresOut(BaseModel):
    trend: Optional[float] = None
    momentum: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    volatility: Optional[float] = None
    risk_reward: Optional[float] = None


class RadarOpportunitySummaryOut(BaseModel):
    """One row in the ranked opportunity list (GET .../radar-v2/
    opportunities) -- only the currently-live (non-superseded)
    opportunity per symbol appears here, ordered by stage1_ranking_score
    descending."""

    id: int
    symbol: str
    company_name_ar: Optional[str] = None
    company_name_en: str

    classification: str
    classification_label_ar: str
    confidence_score: float
    confidence_disclaimer_ar: str = (
        "درجة الثقة تقيس قوة واتساق الأدلة المتاحة، وليست احتمال ربح مضمون."
    )
    # RADAR-C/VAL-8: the same disclosed, additive calibration companion
    # figure the /decision-v2 and /recommendation-history routes already
    # expose -- read straight from the linked DecisionV2Snapshot, which
    # already computes it honestly (None whenever no ACTIVE
    # confidence_calibration_models row exists for the "decision_v2"
    # source; never fabricated). confidence_score above is always the
    # raw score and is never overwritten by this.
    calibrated_confidence_score: Optional[float] = None
    calibration_version: Optional[str] = None

    # Phase 5 (BASIRAH Score): the platform's single unified 0-100
    # opportunity-quality composite (src.analysis.decision_v2.scoring.
    # opportunity_quality_score) -- already computed for every Stage 2
    # candidate, just not previously denormalized onto the Radar API.
    # Distinct from confidence_score (evidence strength/consistency):
    # this blends trend/momentum/volume/liquidity/volatility/risk-reward/
    # market-context/data-quality into one headline number.
    basirah_score: Optional[float] = None

    price_at_signal: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    expected_return_target_1: Optional[float] = None
    risk_reward_target_1: Optional[float] = None

    risk_level: Optional[str] = None
    risk_level_label_ar: Optional[str] = None
    data_freshness_status: str

    # Pre-launch safety fix (2026-08-22): entry_status/entry_status_label_ar
    # were already computed by Decision Engine V2 for every opportunity
    # (src.analysis.decision_v2.trade_classification.classify_entry_status)
    # and already exposed on the Detail payload -- just never surfaced on
    # the list/summary payload the consumer Radar page and cards actually
    # render. Presentation-only exposure of an existing value; no new
    # classification logic. entry_status == "MISSED_ENTRY" is what lets the
    # frontend stop presenting an opportunity as a current actionable entry
    # without touching the underlying decision.
    entry_status: Optional[str] = None
    entry_status_label_ar: Optional[str] = None

    stage1_rank: Optional[int] = None
    stage1_ranking_score: Optional[float] = None
    ranking_reason_ar: Optional[str] = None

    emitted_at: datetime
    # Production freshness fix (2026-08-23): whether this opportunity's
    # `emitted_at` (the decision-computation timestamp, frozen at
    # emission -- see RadarOpportunity's own docstring) still belongs
    # to the current/most recently completed Tadawul session. Distinct
    # from `data_freshness_status` above, which describes the PRICE
    # data the decision was computed from, not the age of the decision
    # itself -- see src.analysis.decision_v2.decision_freshness.
    decision_freshness_status: str = "UNKNOWN"
    is_decision_fresh: bool = False
    decision_v2_snapshot_id: int


class RadarOpportunityDetailOut(RadarOpportunitySummaryOut):
    """GET .../radar-v2/opportunities/{id} -- adds Stage 1's full
    evidence breakdown, the linked decision's reasoning/risk-flags, and
    (when it exists) this opportunity's real-market outcome so far.
    Never a full ~90-column DecisionV2Snapshot dump -- only the fields
    the Radar V2 mandate itself names (technical reasons, liquidity/
    volume evidence, risk flags, horizon).

    Phase 4 (Advanced Technical Engine exposure): trend/support-resistance/
    volume/accumulation/entry-quality/why-now fields below are all
    pre-existing DecisionV2Snapshot columns already computed by Decision
    Engine V2 for every Stage 2 candidate -- this only exposes them, it
    computes nothing new and costs zero additional SAHMK calls. The
    mandate's requested "Intraday" sub-component (VWAP distance, opening-
    range breakout, HOD/LOD) is intentionally NOT included: the platform's
    OHLCV ingestion is once-daily post-close only, so an intraday reading
    cannot be honestly computed from real data today without a new
    (likely paid) data source, which requires explicit user approval."""

    stage1_component_scores: RadarStage1ComponentScoresOut = Field(
        default_factory=RadarStage1ComponentScoresOut
    )
    stage1_signals: List[Stage1SignalOut] = Field(default_factory=list)
    stage1_risk_reward_ratio: Optional[float] = None

    expected_holding_period_min_days: Optional[int] = None
    expected_holding_period_max_days: Optional[int] = None
    expected_holding_period_label_ar: Optional[str] = None

    positive_reasons: List[str] = Field(default_factory=list)
    negative_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendation_basis: Optional[str] = None

    liquidity_quality_ar: Optional[str] = None
    relative_volume: Optional[float] = None
    accumulation_assessment_ar: Optional[str] = None

    trend_direction_ar: Optional[str] = None
    trend_strength_label_ar: Optional[str] = None

    nearest_support: Optional[float] = None
    major_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    major_resistance: Optional[float] = None
    breakout_level: Optional[float] = None
    breakdown_level: Optional[float] = None
    support_resistance_evidence_ar: Optional[str] = None

    current_volume: Optional[float] = None
    average_volume: Optional[float] = None
    accumulation_score: Optional[float] = None

    entry_quality_label_ar: Optional[str] = None
    # entry_status / entry_status_label_ar are inherited from
    # RadarOpportunitySummaryOut (exposed there too as of the pre-launch
    # safety fix above) -- not redeclared here.

    why_now_ar: Optional[str] = None
    why_not_stronger_ar: Optional[str] = None
    why_not_buy_reasons: List[str] = Field(default_factory=list)

    # Phase 5 (Risk Manager + Market/sector context + Signal
    # invalidation exposure): market_risk_state/label_ar are the 9-state
    # market-wide classifier's read at decision time (already computed
    # and gating entries in gates.py -- this only exposes the per-
    # opportunity value alongside the market-wide banner already shown
    # on the Radar home page). sector_ar and invalidation_conditions are
    # likewise pre-existing DecisionV2Snapshot fields with no prior
    # Radar API exposure.
    market_risk_state: Optional[str] = None
    market_risk_label_ar: Optional[str] = None
    sector_ar: Optional[str] = None
    invalidation_conditions: List[str] = Field(default_factory=list)

    decision_timestamp: datetime
    market_status: str

    outcome_status: Optional[str] = None
    outcome_return_pct: Optional[float] = None
    outcome_evaluated_at: Optional[datetime] = None


class RadarV2ScanOut(BaseModel):
    """POST .../radar-v2/scan -- one full Radar V2 pass: Stage 1
    (always zero SAHMK cost) -> hard-capped candidate selection ->
    bounded Stage 2 -> RadarOpportunity emission with dedup.
    `stage2_executed=False` always means no live SAHMK quota was spent
    this call beyond whatever Stage 2's own pre-flight checks already
    cost (zero) -- `stage2_stop_reason` says why."""

    triggered_at: datetime
    stage1_universe_size: int
    stage1_candidate_count: int
    stage2_candidate_cap: int
    stage2_symbols_selected: List[str] = Field(default_factory=list)
    stage2_executed: bool
    stage2_stop_reason: Optional[str] = None
    scan_run_id: Optional[int] = None
    opportunities_emitted: List[RadarOpportunitySummaryOut] = Field(default_factory=list)
    opportunities_suppressed_as_duplicate: List[str] = Field(default_factory=list)


class RadarV2SummaryOut(BaseModel):
    """GET .../radar-v2/summary -- the current state of the radar at a
    glance: how many live opportunities exist and their classification
    mix, without listing each one."""

    generated_at: datetime
    live_opportunity_count: int
    live_by_classification: Dict[str, int] = Field(default_factory=dict)
    average_confidence: Optional[float] = None
    most_recent_scan_run_id: Optional[int] = None
    most_recent_emitted_at: Optional[datetime] = None
    stage2_candidate_cap: int


class RadarV2PerformanceOut(BaseModel):
    """GET .../radar-v2/performance -- Phase B forward-testing metrics,
    computed directly from real DecisionV2Outcome rows. Every rate is
    null (never 0.0) when resolved_count is zero -- a genuine
    not-enough-data-yet state is never presented as a measured 0%."""

    generated_at: datetime
    total_opportunities_emitted: int
    total_outcomes_tracked: int
    pending_count: int
    resolved_count: int
    target_hit_count: int
    stop_loss_hit_count: int
    partial_count: int
    expired_count: int
    data_unavailable_count: int
    target_hit_rate: Optional[float] = None
    stop_loss_hit_rate: Optional[float] = None
    average_return_pct: Optional[float] = None
    live_opportunities_by_classification: Dict[str, int] = Field(default_factory=dict)
    # Post-VAL-8 accumulation phase: the explicit minimum-sample gate
    # (reused from the platform's own DEFAULT_MIN_SAMPLE_SIZE=30, not an
    # arbitrary number) before any statistical claim -- let alone
    # optimization/calibration -- is warranted. accumulation_status is
    # one of INSUFFICIENT_DATA (0 resolved) / PRELIMINARY (below gate) /
    # READY_FOR_CALIBRATION (at or above gate).
    minimum_sample_size_required: int = 30
    sample_size_adequate: bool = False
    accumulation_status: str = "INSUFFICIENT_DATA"


class RadarV2GroupPerformanceOut(BaseModel):
    """One cohort's forward-test statistics. `signal_count` is every real
    DecisionV2Outcome row in the cohort (resolved + unresolved) -- always
    shown alongside any rate so a tiny sample is never mistaken for a
    large one. `target_hit_rate`/`stop_loss_hit_rate` use resolved_count
    as their denominator; `win_rate`/`expectancy_pct` use the
    decisive-only denominator (TARGET_x_HIT vs STOP_LOSS_HIT). Every rate
    is null, never a fabricated 0.0, when its own denominator is zero."""

    label: str
    signal_count: int
    resolved_count: int = 0
    unresolved_count: int = 0
    target_hit_rate: Optional[float] = None
    stop_loss_hit_rate: Optional[float] = None
    win_rate: Optional[float] = None
    average_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    average_favorable_excursion_pct: Optional[float] = None
    average_adverse_excursion_pct: Optional[float] = None
    average_risk_reward_realized: Optional[float] = None
    expectancy_pct: Optional[float] = None
    max_adverse_outcome_pct: Optional[float] = None
    # Whether this cohort alone has reached the platform's minimum
    # sample gate (30 resolved outcomes) -- see RadarV2PerformanceOut.
    sample_size_adequate: bool = False


class RadarV2ExtendedPerformanceOut(BaseModel):
    """GET .../radar-v2/performance/extended -- RADAR-C Phase D: the
    mandate's explicit breakdown questions (win rate by classification/
    confidence-band/market-regime, performance by sector/holding-
    horizon/market segment, MFE/MAE, calibration) over the FULL
    RadarOpportunity/DecisionV2Outcome history, not one ValidationSession
    window. Every group's rate fields are null, not 0.0, until real
    resolved outcomes exist for it."""

    generated_at: datetime
    total_signals_by_classification: Dict[str, int] = Field(default_factory=dict)
    win_rate_by_classification: List[RadarV2GroupPerformanceOut] = Field(default_factory=list)
    win_rate_by_confidence_band: List[RadarV2GroupPerformanceOut] = Field(default_factory=list)
    win_rate_by_market_regime: List[RadarV2GroupPerformanceOut] = Field(default_factory=list)
    performance_by_sector: List[RadarV2GroupPerformanceOut] = Field(default_factory=list)
    performance_by_holding_horizon: List[RadarV2GroupPerformanceOut] = Field(default_factory=list)
    performance_by_market: List[RadarV2GroupPerformanceOut] = Field(default_factory=list)
    average_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    average_favorable_excursion_pct: Optional[float] = None
    average_adverse_excursion_pct: Optional[float] = None
    calibration_pair_count: int = 0
    expected_calibration_error: Optional[float] = None


class DailyValidationReportOut(BaseModel):
    """GET .../radar-v2/daily-validation-report -- BASIRAH LIVE
    VALIDATION TRACKING: every RadarOpportunity emitted on `report_date`
    (one UTC calendar day), tracked to its real, sequence-verified
    outcome resolution so far. `verified_win_rate`/`target_1_hit_rate`/
    `stop_before_target_rate` all share the same rigorous denominator
    (wins + losses among sequence-resolved trades only); an untriggered
    entry, a same-day target/stop tie, and WATCH/HOLD/REJECT/
    WAIT_FOR_ENTRY signals are never counted as failed BUY trades. Every
    rate is null, never a fabricated 0.0, when its denominator is zero."""

    report_date: str
    total_opportunities: int
    actionable_buy_signals: int
    entries_triggered: int
    target_1_wins: int
    target_2_wins: int
    target_3_wins: int
    stop_before_target_losses: int
    open_trades: int
    entries_not_triggered: int
    invalidated: int
    non_actionable_counts: Dict[str, int] = Field(default_factory=dict)
    verified_win_rate: Optional[float] = None
    target_1_hit_rate: Optional[float] = None
    stop_before_target_rate: Optional[float] = None
    verified_sample_size: int = 0


class RadarV2SahmkConsumptionOut(BaseModel):
    """GET .../radar-v2/sahmk-consumption -- SAHMK quota consumption
    attributable specifically to Radar V2, read verbatim from the
    existing per-operation rate-limiter/cache telemetry's "radar_v2"
    breakdown (see src.market_data.sahmk.operation_scope.RADAR_V2) --
    no separate accounting mechanism, no secrets (never includes the
    SAHMK API key or any credential, matching every other admin
    diagnostics route's existing contract)."""

    generated_at: datetime
    rate_limiter_by_operation: Optional[Dict] = None
    cache_by_operation: Optional[Dict] = None
