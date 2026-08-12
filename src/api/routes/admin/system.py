"""GET /api/v1/admin/system/health -- Admin Dashboard "view system
health": real DB (`SELECT 1`) and Redis (`PING`) probes. Deliberately
self-contained (doesn't reach into main.py's module-level `kernel`
global) so it's testable in isolation and has no dependency on the
runtime kernel/worker subsystem, which is orthogonal to "can this
process reach its datastores."
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.api.schemas.admin import AdminDashboardSummaryOut, SystemHealthOut
from src.auth.rbac import require_staff_role
from src.auth.token_store import get_redis_client
from src.core.config import settings
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/system", tags=["admin"])


def _classify_market_data_health(health_snapshot: Dict[str, Any], breaker_state: Optional[str]) -> str:
    """"healthy" | "degraded" | "unhealthy" -- derived entirely from
    already-known state (no network call). A quota-exhausted or
    breaker-open condition is "degraded," not silently "healthy": the
    provider itself may be fine, but this integration currently cannot
    use it."""
    if not health_snapshot.get("sahmk_key_present", True):
        return "unhealthy"
    if breaker_state == "OPEN":
        return "degraded"
    if health_snapshot.get("current_provider_kind") == "sahmk" and health_snapshot.get(
        "last_connectivity_status"
    ) == "SUCCESS":
        return "healthy"
    if health_snapshot.get("current_provider_kind") is None:
        return "unhealthy"
    return "degraded"


def _classify_market_data_status(
    health_snapshot: Dict[str, Any], quota_status: Optional[Dict[str, Any]], breaker_state: Optional[str]
) -> str:
    """"LIVE" | "STALE" | "DEGRADED" | "UNAVAILABLE" -- the honest,
    evidence-based answer to "can a user trust the market data on
    screen right now," never fabricated. Real SAHMK quota exhaustion
    (provider truth, see SahmkRateLimiter.get_status()) always wins
    over an optimistic last_connectivity_status."""
    if quota_status and quota_status.get("upstream_confirmed_exhausted"):
        return "DEGRADED"
    if breaker_state == "OPEN":
        return "DEGRADED"
    kind = health_snapshot.get("current_provider_kind")
    if kind is None:
        return "UNAVAILABLE"
    if kind != "sahmk":
        return "DEGRADED"  # synthetic/dev fallback -- never presented as live real data
    if health_snapshot.get("last_connectivity_status") == "SUCCESS":
        return "LIVE"
    if health_snapshot.get("last_real_data_at") is not None:
        return "STALE"
    return "UNAVAILABLE"


@router.get("/health", response_model=SystemHealthOut)
def get_system_health(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> SystemHealthOut:
    details = {}

    try:
        session.execute(text("SELECT 1"))
        details["database"] = "healthy"
    except Exception as exc:
        logger.error("Admin health check: database probe failed: %s", exc)
        details["database"] = "unhealthy"

    try:
        get_redis_client().ping()
        details["redis"] = "healthy"
    except Exception as exc:
        logger.error("Admin health check: redis probe failed: %s", exc)
        details["redis"] = "unhealthy"

    status = "healthy" if all(v == "healthy" for v in details.values()) else "degraded"
    return SystemHealthOut(status=status, details=details)


@router.get("/summary", response_model=AdminDashboardSummaryOut)
async def get_dashboard_summary(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> AdminDashboardSummaryOut:
    """Consolidated "at a glance" view for the admin dashboard landing
    screen: real values only -- every field here is either read from a
    live probe, a real DB aggregate, or an explicit `None`/`False` when
    something genuinely isn't known/running, never a placeholder."""
    import main  # Lazy: main.py imports this router at module load, so a
    # module-level import here would be circular.
    from src.domain.models import User as UserModel

    try:
        session.execute(text("SELECT 1"))
        database_health = "healthy"
    except Exception as exc:
        logger.error("Admin dashboard summary: database probe failed: %s", exc)
        database_health = "unhealthy"

    try:
        get_redis_client().ping()
        redis_health = "healthy"
    except Exception as exc:
        logger.error("Admin dashboard summary: redis probe failed: %s", exc)
        redis_health = "unhealthy"

    # Deliberately zero-network-call: this used to call
    # get_market_data_provider() + provider.health_check() live, on
    # every dashboard load -- each a real SAHMK connectivity probe
    # (2026-08-10 production evidence: this endpoint was itself
    # burning SAHMK quota just to be viewed, and under STRICT_REAL_DATA
    # a probe failure raised StrictRealDataUnavailableError, silently
    # swallowed by the bare except below into an uninformative None/
    # None -- exactly when a real degraded state most needed to be
    # visible). get_market_data_health() and the two accessors below
    # only ever read state some *other* real call already established;
    # they never touch the network themselves.
    market_data_provider = None
    market_data_health = None
    market_data_status = "UNAVAILABLE"
    market_data_circuit_breaker_state = None
    try:
        from src.market_data.provider_factory import (
            get_cached_provider_circuit_breaker_state,
            get_last_selected_provider_kind,
            get_market_data_health,
        )

        health_snapshot = get_market_data_health()
        market_data_provider = get_last_selected_provider_kind()
        market_data_circuit_breaker_state = get_cached_provider_circuit_breaker_state()
    except Exception as exc:
        logger.error("Admin dashboard summary: market data diagnostics read failed: %s", exc)
        health_snapshot = {}

    try:
        from src.market_data.sahmk.rate_limiter import get_default_rate_limiter

        sahmk_quota_status = get_default_rate_limiter().get_status()
    except Exception as exc:
        logger.error("Admin dashboard summary: SAHMK quota status read failed: %s", exc)
        sahmk_quota_status = None

    try:
        from src.market_data.caching.redis_shared_cache import get_default_sahmk_cache, get_observability_snapshot

        market_data_cache_status = get_observability_snapshot({"sahmk_market_data": get_default_sahmk_cache()})
    except Exception as exc:
        logger.error("Admin dashboard summary: market-data cache status read failed: %s", exc)
        market_data_cache_status = None

    market_data_health = _classify_market_data_health(health_snapshot, market_data_circuit_breaker_state)
    market_data_status = _classify_market_data_status(
        health_snapshot, sahmk_quota_status, market_data_circuit_breaker_state
    )

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    new_users_last_24h = session.query(func.count(UserModel.id)).filter(UserModel.created_at >= day_ago).scalar() or 0
    new_users_last_7d = session.query(func.count(UserModel.id)).filter(UserModel.created_at >= week_ago).scalar() or 0
    logins_last_24h = (
        session.query(func.count(UserModel.id)).filter(UserModel.last_login_at >= day_ago).scalar() or 0
    )
    locked_accounts = (
        session.query(func.count(UserModel.id)).filter(UserModel.locked_until > now).scalar() or 0
    )

    from src.analysis.decision_v2.engine import DECISION_V2_ENGINE_VERSION
    from src.domain.models import (
        IngestionJobStatus,
        IngestionRunLog,
        MarketScanProgress,
        MarketScanRun,
        MarketScanStatus,
    )
    from src.market_data.config import is_strict_real_data_enabled
    from src.market_intelligence.market_status import get_market_status

    # Mirrors admin/market_intelligence.py's own _INGESTION_JOB_NAMES --
    # duplicated here (not imported) since that name is private to its
    # module; the four ingestion jobs are otherwise not enumerated
    # anywhere shared. Surfaces the same DEFERRED-status signal
    # /coverage already exposes per-job, but as a single at-a-glance
    # "is anything currently quota-deferred, and when will it retry"
    # pair for the dashboard landing screen -- staff previously had no
    # way to see this without navigating to the market-coverage page.
    ingestion_deferred_job_count = 0
    ingestion_next_retry_at = None
    for _job_name in ("symbols", "historical_ohlcv", "fundamentals", "dividends"):
        _latest_run = (
            session.query(IngestionRunLog)
            .filter(IngestionRunLog.job_name == _job_name)
            .order_by(IngestionRunLog.id.desc())
            .first()
        )
        if (
            _latest_run is not None
            and _latest_run.status is IngestionJobStatus.DEFERRED
            and _latest_run.next_retry_at is not None
        ):
            ingestion_deferred_job_count += 1
            _retry_at = _latest_run.next_retry_at
            if _retry_at.tzinfo is None:
                # Same SQLite naive-datetime pitfall documented elsewhere
                # (e.g. IngestionScheduler._compute_initial_delay) --
                # next_retry_at is always written as UTC, so a naive
                # value read back is treated as UTC rather than compared
                # against an aware datetime incorrectly.
                _retry_at = _retry_at.replace(tzinfo=timezone.utc)
            if ingestion_next_retry_at is None or _retry_at < ingestion_next_retry_at:
                ingestion_next_retry_at = _retry_at

    last_scan = (
        session.query(MarketScanRun).order_by(MarketScanRun.created_at.desc()).first()
    )
    last_scan_progress = (
        session.query(MarketScanProgress).filter(MarketScanProgress.run_id == last_scan.id).first()
        if last_scan is not None
        else None
    )
    scan_lock_active = (
        session.query(MarketScanRun.id)
        .filter(MarketScanRun.status.in_([MarketScanStatus.PENDING, MarketScanStatus.RUNNING]))
        .first()
        is not None
    )
    market_info = get_market_status()

    return AdminDashboardSummaryOut(
        app_version=main.app.version,
        deployment_commit=settings.deployment_commit,
        environment=settings.environment,
        database_health=database_health,
        redis_health=redis_health,
        ingestion_scheduler_running=main.ingestion_scheduler is not None and main.ingestion_scheduler.is_running,
        ingestion_deferred_job_count=ingestion_deferred_job_count,
        ingestion_next_retry_at=(
            ingestion_next_retry_at.isoformat() if ingestion_next_retry_at is not None else None
        ),
        market_intelligence_scheduler_running=(
            main.market_intelligence_scheduler is not None and main.market_intelligence_scheduler.is_running
        ),
        live_market_mode_enabled=main.live_market_mode_scheduler is not None,
        live_market_mode_running=(
            main.live_market_mode_scheduler is not None and main.live_market_mode_scheduler.is_running
        ),
        live_market_mode_market_currently_open=(
            main.live_market_mode_scheduler is not None and main.live_market_mode_scheduler.is_market_currently_open
        ),
        market_data_provider=market_data_provider,
        market_data_health=market_data_health,
        market_data_status=market_data_status,
        market_data_circuit_breaker_state=market_data_circuit_breaker_state,
        market_data_last_connectivity_status=health_snapshot.get("last_connectivity_status"),
        market_data_last_connectivity_at=health_snapshot.get("last_connectivity_at"),
        market_data_last_real_data_at=health_snapshot.get("last_real_data_at"),
        new_users_last_24h=new_users_last_24h,
        new_users_last_7d=new_users_last_7d,
        logins_last_24h=logins_last_24h,
        locked_accounts=locked_accounts,
        last_scan_id=last_scan.id if last_scan else None,
        last_scan_status=last_scan.status.value if last_scan else None,
        last_scan_started_at=last_scan.started_at if last_scan else None,
        last_scan_finished_at=last_scan.finished_at if last_scan else None,
        last_scan_symbols_requested=last_scan.symbols_requested if last_scan else None,
        last_scan_symbols_succeeded=last_scan.symbols_succeeded if last_scan else None,
        last_scan_symbols_failed=last_scan.symbols_failed if last_scan else None,
        last_scan_published_count=last_scan_progress.published_count if last_scan_progress else None,
        last_scan_watch_only_count=last_scan_progress.watch_only_count if last_scan_progress else None,
        last_scan_rejected_count=last_scan_progress.rejected_count if last_scan_progress else None,
        last_scan_insufficient_data_count=(
            last_scan_progress.insufficient_data_count if last_scan_progress else None
        ),
        last_scan_latest_error=(
            last_scan_progress.latest_error if last_scan_progress
            else (last_scan.error_summary if last_scan else None)
        ),
        decision_engine_version=DECISION_V2_ENGINE_VERSION,
        market_status=market_info.status.value,
        market_status_label_ar=market_info.label_ar,
        strict_real_data_enforced=is_strict_real_data_enabled(),
        scan_lock_active=scan_lock_active,
        sahmk_quota_status=sahmk_quota_status,
        market_data_cache_status=market_data_cache_status,
    )
