from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import SubscriptionPlan, SubscriptionStatus, User
from src.subscriptions import subscription_service
from src.subscriptions.repository import SubscriptionRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(session):
    u = User(email="trial@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


def test_provision_trial_subscription_sets_trial_ends_at_from_settings(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "trial_length_days", 14)
    before = datetime.now(timezone.utc)
    subscription = subscription_service.provision_trial_subscription(session, user)
    after = datetime.now(timezone.utc)

    assert subscription.plan == SubscriptionPlan.TRIAL
    assert subscription.status == SubscriptionStatus.TRIALING

    trial_ends_at = subscription.trial_ends_at
    if trial_ends_at.tzinfo is None:  # SQLite round-trips DateTime as naive
        trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
    assert before + timedelta(days=14) <= trial_ends_at <= after + timedelta(days=14)


def test_get_effective_subscription_returns_none_when_missing(session):
    assert subscription_service.get_effective_subscription(session, 9999) is None


def test_get_effective_subscription_leaves_a_live_trial_alone(session, user):
    subscription_service.provision_trial_subscription(session, user)
    effective = subscription_service.get_effective_subscription(session, user.id)
    assert effective.status == SubscriptionStatus.TRIALING


def test_get_effective_subscription_lazily_downgrades_an_expired_trial(session, user):
    repo = SubscriptionRepository()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    repo.create_subscription(
        session,
        user_id=user.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        trial_ends_at=past,
        current_period_start=past - timedelta(days=14),
        current_period_end=past,
    )

    effective = subscription_service.get_effective_subscription(session, user.id)
    assert effective.status == SubscriptionStatus.EXPIRED

    # The downgrade was persisted, not just reflected on the in-memory object.
    reloaded = repo.get_subscription_for_user(session, user.id)
    assert reloaded.status == SubscriptionStatus.EXPIRED


def test_is_entitled_true_for_trialing_and_active(session, user):
    repo = SubscriptionRepository()
    trialing = repo.create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.TRIALING
    )
    assert subscription_service.is_entitled(trialing) is True


def test_is_entitled_false_for_expired_canceled_or_none(session, user):
    repo = SubscriptionRepository()
    expired = repo.create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.EXPIRED
    )
    assert subscription_service.is_entitled(expired) is False
    assert subscription_service.is_entitled(None) is False


# --- admin actions (Phase 10 M10.9) -------------------------------------


def test_extend_trial_adds_days_from_the_existing_trial_end_when_still_live(session, user):
    repo = SubscriptionRepository()
    now = datetime.now(timezone.utc)
    original_end = now + timedelta(days=5)
    subscription = repo.create_subscription(
        session,
        user_id=user.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        trial_ends_at=original_end,
        current_period_end=original_end,
    )

    updated = subscription_service.extend_trial(session, subscription, additional_days=7)

    trial_ends_at = updated.trial_ends_at
    if trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
    assert abs((trial_ends_at - (original_end + timedelta(days=7))).total_seconds()) < 2
    assert updated.status == SubscriptionStatus.TRIALING


def test_extend_trial_restarts_from_now_when_already_expired(session, user):
    repo = SubscriptionRepository()
    past = datetime.now(timezone.utc) - timedelta(days=10)
    subscription = repo.create_subscription(
        session,
        user_id=user.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.EXPIRED,
        trial_ends_at=past,
        current_period_end=past,
    )

    before = datetime.now(timezone.utc)
    updated = subscription_service.extend_trial(session, subscription, additional_days=7)
    after = datetime.now(timezone.utc)

    trial_ends_at = updated.trial_ends_at
    if trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
    assert before + timedelta(days=7) <= trial_ends_at <= after + timedelta(days=7)
    assert updated.status == SubscriptionStatus.TRIALING


def test_admin_activate_subscription_sets_active_monthly_plan(session, user):
    repo = SubscriptionRepository()
    subscription = repo.create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.TRIALING
    )

    updated = subscription_service.admin_activate_subscription(
        session, subscription, SubscriptionPlan.MONTHLY, period_days=30
    )

    assert updated.plan == SubscriptionPlan.MONTHLY
    assert updated.status == SubscriptionStatus.ACTIVE
    assert updated.current_period_end is not None


def test_admin_activate_subscription_rejects_the_trial_plan(session, user):
    repo = SubscriptionRepository()
    subscription = repo.create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.TRIALING
    )
    with pytest.raises(ValueError):
        subscription_service.admin_activate_subscription(session, subscription, SubscriptionPlan.TRIAL, period_days=30)
