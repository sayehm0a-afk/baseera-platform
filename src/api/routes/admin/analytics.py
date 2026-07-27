"""GET /api/v1/admin/analytics -- Admin Dashboard "view analytics,"
real COUNT() aggregates only (no fabricated metrics)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.schemas.admin import AnalyticsOut
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import BacktestRun, Portfolio, StaffRole, Subscription, User

router = APIRouter(prefix="/api/v1/admin/analytics", tags=["admin"])


@router.get("", response_model=AnalyticsOut)
def get_analytics(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> AnalyticsOut:
    total_users = session.query(func.count(User.id)).scalar() or 0

    staff_role_rows = (
        session.query(User.staff_role, func.count(User.id)).filter(User.is_staff.is_(True)).group_by(User.staff_role).all()
    )
    users_by_staff_role = {role.value: count for role, count in staff_role_rows if role is not None}

    status_rows = session.query(Subscription.status, func.count(Subscription.id)).group_by(Subscription.status).all()
    subscriptions_by_status = {status.value: count for status, count in status_rows}

    plan_rows = session.query(Subscription.plan, func.count(Subscription.id)).group_by(Subscription.plan).all()
    subscriptions_by_plan = {plan.value: count for plan, count in plan_rows}

    total_portfolios = session.query(func.count(Portfolio.id)).scalar() or 0
    total_backtest_runs = session.query(func.count(BacktestRun.id)).scalar() or 0

    return AnalyticsOut(
        total_users=total_users,
        users_by_staff_role=users_by_staff_role,
        subscriptions_by_status=subscriptions_by_status,
        subscriptions_by_plan=subscriptions_by_plan,
        total_portfolios=total_portfolios,
        total_backtest_runs=total_backtest_runs,
    )
