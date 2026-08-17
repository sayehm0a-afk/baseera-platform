"""Response/request schemas for /api/v1/admin/*."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    is_email_verified: bool
    is_active: bool
    is_staff: bool
    staff_role: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUserListOut(BaseModel):
    total: int
    users: List[AdminUserOut]


class SetStaffRoleRequest(BaseModel):
    is_staff: bool
    staff_role: Optional[str] = Field(default=None, pattern="^(OWNER|ADMIN|SUPPORT)$")

    @model_validator(mode="after")
    def _staff_role_required_iff_is_staff(self) -> "SetStaffRoleRequest":
        if self.is_staff and self.staff_role is None:
            raise ValueError("staff_role is required when is_staff is true.")
        if not self.is_staff and self.staff_role is not None:
            raise ValueError("staff_role must be omitted when is_staff is false.")
        return self


class AdminSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plan: str
    status: str
    trial_ends_at: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool


class AdminSubscriptionListOut(BaseModel):
    total: int
    subscriptions: List[AdminSubscriptionOut]


class AdminPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount: float
    status: str
    provider_transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AdminInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: Optional[int] = None
    amount: float
    currency: str
    status: str
    provider: str
    provider_reference: Optional[str] = None
    issued_at: datetime
    paid_at: Optional[datetime] = None


class AdminInvoiceListOut(BaseModel):
    total: int
    invoices: List[AdminInvoiceOut]


class AdminPaymentListOut(BaseModel):
    payments: List[AdminPaymentOut]


class ExtendTrialRequest(BaseModel):
    additional_days: int = Field(gt=0, le=365)


class ActivateSubscriptionRequest(BaseModel):
    plan: str = Field(pattern="^(MONTHLY|YEARLY)$")
    period_days: int = Field(gt=0, le=366)


class CancelSubscriptionRequest(BaseModel):
    immediately: bool = False


class AdminSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    device_label: Optional[str] = None
    ip_address: Optional[str] = None
    issued_at: datetime
    last_used_at: datetime
    expires_at: datetime


class AdminSessionListOut(BaseModel):
    total: int
    sessions: List[AdminSessionOut]


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    severity: str
    starts_at: datetime
    ends_at: Optional[datetime] = None
    is_active: bool
    created_by_user_id: int
    created_at: datetime


class AnnouncementListOut(BaseModel):
    announcements: List[AnnouncementOut]


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    severity: str = Field(default="INFO", pattern="^(INFO|WARNING|CRITICAL)$")
    starts_at: datetime
    ends_at: Optional[datetime] = None


class AnnouncementUpdateRequest(BaseModel):
    is_active: Optional[bool] = None


class FeatureFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    enabled: bool
    description: Optional[str] = None


class FeatureFlagListOut(BaseModel):
    feature_flags: List[FeatureFlagOut]


class FeatureFlagCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    enabled: bool = False
    description: Optional[str] = None


class FeatureFlagUpdateRequest(BaseModel):
    enabled: bool


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int
    action: str
    target_type: str
    target_id: Optional[int] = None
    details_json: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime


class AuditLogListOut(BaseModel):
    total: int
    logs: List[AuditLogOut]


class AIUsageSummaryOut(BaseModel):
    total_requests: int
    success_count: int
    failed_count: int
    timeout_count: int
    total_tokens: int
    estimated_cost_usd: float
    by_feature: Dict[str, int]


class AnalyticsOut(BaseModel):
    total_users: int
    users_by_staff_role: Dict[str, int]
    subscriptions_by_status: Dict[str, int]
    subscriptions_by_plan: Dict[str, int]
    total_portfolios: int
    total_backtest_runs: int


class SystemHealthOut(BaseModel):
    status: str
    details: Dict[str, Any]


class AdminDashboardSummaryOut(BaseModel):
    app_version: str
    deployment_commit: Optional[str] = None
    environment: str
    database_health: str
    redis_health: str
    ingestion_scheduler_running: bool
    # True only for the single Gunicorn worker currently holding the
    # Redis leader lease (basirah:ingestion_scheduler:leader) -- see
    # src.market_intelligence.scheduler_leader_lock.SchedulerLeaderLock
    # and IngestionScheduler's leadership heartbeat. False on every
    # other worker sharing the same process pool: they keep
    # ingestion_scheduler_running=True (their job loops are alive and
    # ticking) but skip the actual SAHMK-consuming work, so a fleet of
    # N workers never multiplies ingestion quota usage by N.
    ingestion_scheduler_is_leader: bool = False
    # Cumulative count of job-loop ticks this worker skipped doing real
    # ingestion work on because it was not the leader at that moment
    # (see ingestion_scheduler_is_leader). Only ever non-zero on
    # follower workers; a healthy leader's own count stays 0. Resets to
    # 0 on process restart -- a per-worker-lifetime counter, not a
    # historical total.
    ingestion_scheduler_skipped_due_to_not_leader_count: int = 0
    # How many of the four ingestion jobs (symbols/historical_ohlcv/
    # fundamentals/dividends) most recently ran and are currently
    # DEFERRED (SAHMK background-quota protection, not a genuine
    # defect -- see src.market_data.ingestion.scheduler) plus the
    # earliest time any of them will retry. 0/None means nothing is
    # currently deferred, not "unknown" -- distinct from
    # ingestion_scheduler_running, which only says the scheduler
    # process itself is alive, not whether its jobs are keeping up.
    ingestion_deferred_job_count: int = 0
    ingestion_next_retry_at: Optional[str] = None
    market_intelligence_scheduler_running: bool

    # Live Market Mode owns its own internal ingestion/scan scheduler
    # instances instead of the two standalone globals above (see
    # main.py's startup wiring) -- without these fields, the two flags
    # above would silently report False forever once Live Market Mode
    # is enabled, even while it's actively scheduling real work. Real
    # main.live_market_mode_scheduler state, never inferred.
    live_market_mode_enabled: bool = False
    live_market_mode_running: bool = False
    live_market_mode_market_currently_open: bool = False

    market_data_provider: Optional[str] = None
    market_data_health: Optional[str] = None

    # Real-provider observability additions -- all read-only, zero-
    # network-call snapshots of state some other real call already
    # established (never a fresh SAHMK probe just to view this
    # dashboard). market_data_status is the honest "can a user trust
    # what's on screen right now" answer: LIVE | STALE | DEGRADED |
    # UNAVAILABLE (see _classify_market_data_status in the route),
    # never fabricated as healthy when SAHMK's own real quota-exhaustion
    # evidence (sahmk_quota_status.upstream_confirmed_exhausted) or an
    # OPEN circuit breaker say otherwise.
    market_data_status: str = "UNAVAILABLE"
    market_data_circuit_breaker_state: Optional[str] = None
    market_data_last_connectivity_status: Optional[str] = None
    market_data_last_connectivity_at: Optional[str] = None
    market_data_last_real_data_at: Optional[str] = None

    new_users_last_24h: int
    new_users_last_7d: int
    logins_last_24h: int
    locked_accounts: int

    # Practical-testing additions: real state of the most recent market
    # scan, so the owner status panel can show "last successful scan"
    # without a second round trip.
    last_scan_id: Optional[int] = None
    last_scan_status: Optional[str] = None
    last_scan_started_at: Optional[datetime] = None
    last_scan_finished_at: Optional[datetime] = None
    last_scan_symbols_requested: Optional[int] = None
    last_scan_symbols_succeeded: Optional[int] = None
    last_scan_symbols_failed: Optional[int] = None

    # Phase 1 Decision Engine V2 additions: publication outcome
    # breakdown for the last scan (from MarketScanProgress, tracked
    # per-symbol as the scan runs -- see that model's own columns),
    # the decision engine version actually deployed, current Tadawul
    # market status, whether STRICT_REAL_DATA is enforced, the latest
    # scan error (if any), and whether a scan is currently locked
    # (PENDING/RUNNING) so a manual scan trigger can be disabled.
    last_scan_published_count: Optional[int] = None
    last_scan_watch_only_count: Optional[int] = None
    last_scan_rejected_count: Optional[int] = None
    last_scan_insufficient_data_count: Optional[int] = None
    last_scan_latest_error: Optional[str] = None
    decision_engine_version: str
    market_status: str
    market_status_label_ar: str
    strict_real_data_enforced: bool
    scan_lock_active: bool

    # SAHMK request-budget visibility -- see
    # src.market_data.sahmk.rate_limiter.SahmkRateLimiter.get_status()'s
    # docstring. Reconciled against real cross-worker Redis-persisted
    # counts when Redis is reachable (quota_shared_across_workers=True
    # in the payload), and against SAHMK's own real 429 evidence
    # (upstream_confirmed_exhausted/upstream_reset_at_utc/
    # upstream_exhaustion_evidence) -- remaining_today is forced to 0
    # whenever that evidence says the account is exhausted, regardless
    # of what the optimistic local count would otherwise show. None
    # only if the rate limiter itself could not be read, never a
    # placeholder for "unknown."
    sahmk_quota_status: Optional[Dict[str, Any]] = None

    # Cross-worker shared market-data cache observability -- see
    # src.market_data.caching.redis_shared_cache.get_observability_snapshot().
    # `backend_health` is one of "healthy"/"degraded"/"disabled" (never
    # a raw Redis error message); `by_namespace` carries only aggregate
    # counters (hits/misses/coalesced_waits/provider_calls/redis_errors),
    # never a credential or connection string. None only if this read
    # itself failed, never a placeholder for "unknown."
    market_data_cache_status: Optional[Dict[str, Any]] = None
