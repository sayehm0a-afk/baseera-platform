"""SubscriptionRepository: the only module that reads/writes the
`subscriptions` table -- persistence only, business rules (trial
provisioning, lazy expiry) live in subscription_service.py, the same
split every other package in this codebase already uses."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Subscription, SubscriptionPlan, SubscriptionStatus


class SubscriptionRepository:
    def create_subscription(
        self,
        session: Session,
        user_id: int,
        plan: SubscriptionPlan,
        status: SubscriptionStatus,
        trial_ends_at: Optional[datetime] = None,
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None,
    ) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            plan=plan,
            status=status,
            trial_ends_at=trial_ends_at,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
        )
        session.add(subscription)
        session.commit()
        return subscription

    def get_subscription_for_user(self, session: Session, user_id: int) -> Optional[Subscription]:
        return session.query(Subscription).filter_by(user_id=user_id).one_or_none()

    def get_subscription(self, session: Session, subscription_id: int) -> Optional[Subscription]:
        return session.query(Subscription).filter_by(id=subscription_id).one_or_none()

    def list_all_subscriptions(
        self, session: Session, limit: int, offset: int
    ) -> Tuple[int, List[Subscription]]:
        """For the admin `GET /api/v1/admin/subscriptions` endpoint."""
        query = session.query(Subscription).order_by(Subscription.id)
        total = query.count()
        return total, query.offset(offset).limit(limit).all()

    def set_status(self, session: Session, subscription_id: int, status: SubscriptionStatus) -> None:
        session.query(Subscription).filter_by(id=subscription_id).update(
            {"status": status, "updated_at": datetime.now(timezone.utc)}
        )
        session.commit()

    def update_trial_ends_at(self, session: Session, subscription_id: int, trial_ends_at: datetime) -> None:
        session.query(Subscription).filter_by(id=subscription_id).update(
            {
                "trial_ends_at": trial_ends_at,
                "current_period_end": trial_ends_at,
                "status": SubscriptionStatus.TRIALING,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        session.commit()

    def set_plan_and_status(
        self,
        session: Session,
        subscription_id: int,
        plan: SubscriptionPlan,
        status: SubscriptionStatus,
        current_period_start: datetime,
        current_period_end: datetime,
    ) -> None:
        session.query(Subscription).filter_by(id=subscription_id).update(
            {
                "plan": plan,
                "status": status,
                "current_period_start": current_period_start,
                "current_period_end": current_period_end,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        session.commit()
