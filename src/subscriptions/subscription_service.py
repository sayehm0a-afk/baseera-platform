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
from src.core.monitoring.prometheus_metrics import get_metrics
from src.domain.models import Subscription, SubscriptionPlan, SubscriptionStatus, User
from src.subscriptions.repository import SubscriptionRepository

_repository = SubscriptionRepository()

_ENTITLED_STATUSES = (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED)


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
        was_trialing = subscription.status == SubscriptionStatus.TRIALING
        _repository.set_status(session, subscription.id, SubscriptionStatus.EXPIRED)
        subscription.status = SubscriptionStatus.EXPIRED
        if was_trialing:
            get_metrics().record_trial_expiration()

    return subscription


def is_entitled(subscription: Optional[Subscription]) -> bool:
    """Whether `subscription` currently grants premium access. Always
    call `get_effective_subscription` first so a stale TRIALING/ACTIVE
    row has already been lazily downgraded -- this function only reads
    `.status`, it never re-checks the period itself."""
    return subscription is not None and subscription.status in _ENTITLED_STATUSES


def extend_trial(session: Session, subscription: Subscription, additional_days: int) -> Subscription:
    """Admin action: pushes `trial_ends_at` (and `current_period_end`)
    forward by `additional_days` from whichever is later -- *now* or
    the subscription's current `trial_ends_at` -- so extending an
    already-expired trial correctly restarts it from today, while
    extending a still-live trial adds to its existing remaining time
    rather than shortening it."""
    now = datetime.now(timezone.utc)
    current_trial_ends_at = subscription.trial_ends_at
    if current_trial_ends_at is not None and current_trial_ends_at.tzinfo is None:
        current_trial_ends_at = current_trial_ends_at.replace(tzinfo=timezone.utc)
    base = max(now, current_trial_ends_at) if current_trial_ends_at is not None else now

    new_trial_ends_at = base + timedelta(days=additional_days)
    _repository.update_trial_ends_at(session, subscription.id, new_trial_ends_at)
    subscription.trial_ends_at = new_trial_ends_at
    subscription.current_period_end = new_trial_ends_at
    subscription.status = SubscriptionStatus.TRIALING
    return subscription


def cancel_subscription(session: Session, subscription: Subscription, immediately: bool = False) -> Subscription:
    """Admin action: cancels a subscription. By default (`immediately=False`,
    the standard "cancel at period end" behavior most subscription
    products use) the customer keeps entitled access until
    `current_period_end` -- only the status changes to CANCELED, which
    `_ENTITLED_STATUSES` still honors as a still-live status *at read
    time*, but `get_effective_subscription()` will lazily downgrade it to
    EXPIRED the moment the period actually passes, exactly like an
    ACTIVE/TRIALING subscription already does. `immediately=True` cuts
    access off right now by also pulling `current_period_end` back to
    the current time, so the very next `get_effective_subscription()` call
    lazily downgrades it to EXPIRED."""
    now = datetime.now(timezone.utc)
    period_end = now if immediately else subscription.current_period_end
    _repository.set_status_and_period_end(session, subscription.id, SubscriptionStatus.CANCELED, period_end)
    subscription.status = SubscriptionStatus.CANCELED
    subscription.current_period_end = period_end
    return subscription


def admin_activate_subscription(
    session: Session, subscription: Subscription, plan: SubscriptionPlan, period_days: int
) -> Subscription:
    """Admin action: manually activates a paid plan for `period_days`
    from today -- e.g. a comped account, or confirming payment received
    outside this system (bank transfer) before a real payment gateway
    exists (M10.7). This is an explicit admin override, not a fake
    payment: no Invoice/Payment row is created, and the distinction
    from a real gateway-confirmed activation is exactly that -- an
    admin, not a payment provider, vouched for this."""
    if plan == SubscriptionPlan.TRIAL:
        raise ValueError("admin_activate_subscription cannot activate the TRIAL plan -- use extend_trial instead.")

    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=period_days)
    _repository.set_plan_and_status(
        session,
        subscription.id,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=period_end,
    )
    subscription.plan = plan
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = period_end
    return subscription
