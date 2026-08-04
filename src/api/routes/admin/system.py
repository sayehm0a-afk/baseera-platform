"""GET /api/v1/admin/system/health -- Admin Dashboard "view system
health": real DB (`SELECT 1`) and Redis (`PING`) probes. Deliberately
self-contained (doesn't reach into main.py's module-level `kernel`
global) so it's testable in isolation and has no dependency on the
runtime kernel/worker subsystem, which is orthogonal to "can this
process reach its datastores."
"""

import logging
from datetime import datetime, timedelta, timezone

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

    market_data_provider = None
    market_data_health = None
    try:
        from src.market_data.provider_factory import get_last_selected_provider_kind, get_market_data_provider

        market_provider = await get_market_data_provider()
        market_data_provider = get_last_selected_provider_kind()
        market_data_health = (await market_provider.health_check()).value
    except Exception as exc:
        logger.error("Admin dashboard summary: market data provider probe failed: %s", exc)

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

    from src.domain.models import MarketScanRun

    last_scan = (
        session.query(MarketScanRun).order_by(MarketScanRun.created_at.desc()).first()
    )

    return AdminDashboardSummaryOut(
        app_version=main.app.version,
        deployment_commit=settings.deployment_commit,
        environment=settings.environment,
        database_health=database_health,
        redis_health=redis_health,
        ingestion_scheduler_running=main.ingestion_scheduler is not None and main.ingestion_scheduler.is_running,
        market_intelligence_scheduler_running=(
            main.market_intelligence_scheduler is not None and main.market_intelligence_scheduler.is_running
        ),
        market_data_provider=market_data_provider,
        market_data_health=market_data_health,
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
    )
