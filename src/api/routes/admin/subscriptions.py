"""GET/POST /api/v1/admin/subscriptions/* -- Admin Dashboard
subscription management: view subscriptions, extend a trial, manually
activate a paid plan. "Activate" is an explicit admin override (comped
account, or payment confirmed outside this system before a real
gateway exists -- M10.7) -- it never creates a fake Invoice/Payment,
and is clearly distinguishable in AuditLog from anything a real
payment webhook would do.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.admin.audit_log import record_admin_action
from src.admin.exceptions import AdminSubscriptionNotFoundError, AdminUserNotFoundError
from src.api.schemas.admin import (
    ActivateSubscriptionRequest,
    AdminSubscriptionListOut,
    AdminSubscriptionOut,
    ExtendTrialRequest,
)
from src.auth.rbac import require_staff_role
from src.auth.repository import AuthRepository
from src.core.db.database import get_db
from src.domain.models import SubscriptionPlan, StaffRole, User
from src.subscriptions import subscription_service
from src.subscriptions.repository import SubscriptionRepository

router = APIRouter(prefix="/api/v1/admin/subscriptions", tags=["admin"])

_repository = SubscriptionRepository()
_auth_repository = AuthRepository()


def _client_ip(request: Request) -> "str | None":
    return request.client.host if request.client else None


@router.get("", response_model=AdminSubscriptionListOut)
def list_subscriptions(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminSubscriptionListOut:
    total, subscriptions = _repository.list_all_subscriptions(session, limit=limit, offset=offset)
    return AdminSubscriptionListOut(
        total=total, subscriptions=[AdminSubscriptionOut.model_validate(s) for s in subscriptions]
    )


@router.get("/{user_id}", response_model=AdminSubscriptionOut)
def get_subscription_for_user(
    user_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminSubscriptionOut:
    if _auth_repository.get_user_by_id(session, user_id) is None:
        raise AdminUserNotFoundError(f"No user {user_id}.")
    subscription = _repository.get_subscription_for_user(session, user_id)
    if subscription is None:
        raise AdminSubscriptionNotFoundError(f"No subscription for user {user_id}.")
    return AdminSubscriptionOut.model_validate(subscription)


@router.post("/{user_id}/extend-trial", response_model=AdminSubscriptionOut)
def extend_trial(
    user_id: int,
    body: ExtendTrialRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminSubscriptionOut:
    subscription = _repository.get_subscription_for_user(session, user_id)
    if subscription is None:
        raise AdminSubscriptionNotFoundError(f"No subscription for user {user_id}.")

    updated = subscription_service.extend_trial(session, subscription, body.additional_days)
    record_admin_action(
        session,
        current_user.id,
        "subscription.extend_trial",
        "subscription",
        target_id=subscription.id,
        details={"additional_days": body.additional_days, "user_id": user_id},
        ip_address=_client_ip(request),
    )
    return AdminSubscriptionOut.model_validate(updated)


@router.post("/{user_id}/activate", response_model=AdminSubscriptionOut)
def activate_subscription(
    user_id: int,
    body: ActivateSubscriptionRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminSubscriptionOut:
    subscription = _repository.get_subscription_for_user(session, user_id)
    if subscription is None:
        raise AdminSubscriptionNotFoundError(f"No subscription for user {user_id}.")

    updated = subscription_service.admin_activate_subscription(
        session, subscription, SubscriptionPlan(body.plan), body.period_days
    )
    record_admin_action(
        session,
        current_user.id,
        "subscription.admin_activate",
        "subscription",
        target_id=subscription.id,
        details={"plan": body.plan, "period_days": body.period_days, "user_id": user_id},
        ip_address=_client_ip(request),
    )
    return AdminSubscriptionOut.model_validate(updated)
