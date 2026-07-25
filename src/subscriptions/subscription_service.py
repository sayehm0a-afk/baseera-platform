"""SubscriptionService: trial auto-provisioning and lazy trial/period
expiry -- the business rules layer over SubscriptionRepository.

Lazy downgrade (Phase 10 plan, decision 9): there is no scheduler
dependency for correctness -- `get_effective_subscription` checks
whether the current period has passed every time it's called (from
`src.auth.rbac.require_active_subscription`) and downgrades the row to
EXPIRED in the same call if so. A subscription is never "wrong" for
longer than the time between two requests. A nightly reconciliation
job (not implemented in this milestone) would only exist for admin
reporting ("who expired today"), never for correctness.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.core.config import settings
from src.domain.models import Subscription, SubscriptionPlan, SubscriptionStatus, User
from src.subscriptions.repository import SubscriptionRepository

_repository = SubscriptionRepository()

_ENTITLED_STATUSES = (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE)


def provision_trial_subscription(session: Session, user: User) -> Subscription:
    """Called once, from src.auth.user_service.register -- every new
    user gets exactly one Subscription row (unique on user_id), never
    created lazily or on-demand elsewhere."""
    now = datetime.now(timezone.utc)
    trial_ends_at = now + timedelta(days=settings.trial_length_days)
    return _repository.create_subscription(
        session,
        user_id=user.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        trial_ends_at=trial_ends_at,
        current_period_start=now,
        current_period_end=trial_ends_at,
    )


def _is_period_expired(subscription: Subscription, now: datetime) -> bool:
    period_end = subscription.current_period_end
    if period_end is None:
        return False
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    return period_end < now


def get_effective_subscription(session: Session, user_id: int) -> Optional[Subscription]:
    """Returns the user's subscription with its status already
    reconciled against the current time -- callers never need to
    re-check `current_period_end` themselves. Returns None only if no
    subscription row exists at all (should not happen for a normally-
    registered user; treated as "not entitled," not an error)."""
    subscription = _repository.get_subscription_for_user(session, user_id)
    if subscription is None:
        return None

    now = datetime.now(timezone.utc)
    if subscription.status in _ENTITLED_STATUSES and _is_period_expired(subscription, now):
        _repository.set_status(session, subscription.id, SubscriptionStatus.EXPIRED)
        subscription.status = SubscriptionStatus.EXPIRED

    return subscription


def is_entitled(subscription: Optional[Subscription]) -> bool:
    """Whether `subscription` currently grants premium access. Always
    call `get_effective_subscription` first so a stale TRIALING/ACTIVE
    row has already been lazily downgraded -- this function only reads
    `.status`, it never re-checks the period itself."""
    return subscription is not None and subscription.status in _ENTITLED_STATUSES
