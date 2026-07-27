from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import SubscriptionPlan, SubscriptionStatus, User
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
def repo():
    return SubscriptionRepository()


@pytest.fixture
def user(session):
    u = User(email="sub@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


def test_create_and_get_subscription(session, repo, user):
    now = datetime.now(timezone.utc)
    trial_ends_at = now + timedelta(days=14)
    subscription = repo.create_subscription(
        session,
        user_id=user.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        trial_ends_at=trial_ends_at,
        current_period_start=now,
        current_period_end=trial_ends_at,
    )
    fetched = repo.get_subscription_for_user(session, user.id)
    assert fetched.id == subscription.id
    assert fetched.plan == SubscriptionPlan.TRIAL
    assert fetched.status == SubscriptionStatus.TRIALING


def test_get_subscription_returns_none_when_missing(session, repo):
    assert repo.get_subscription_for_user(session, 9999) is None


def test_set_status(session, repo, user):
    subscription = repo.create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.TRIALING
    )
    repo.set_status(session, subscription.id, SubscriptionStatus.EXPIRED)
    assert repo.get_subscription_for_user(session, user.id).status == SubscriptionStatus.EXPIRED
