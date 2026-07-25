"""Unit tests for the auth domain models -- User, UserSession,
EmailVerificationToken, PasswordResetToken. Round-trip persistence, no
network.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    EmailVerificationToken,
    PasswordResetToken,
    StaffRole,
    User,
    UserSession,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(session):
    u = User(email="investor@example.com", password_hash="hashed-value")
    session.add(u)
    session.commit()
    return u


# --- User ------------------------------------------------------------------


def test_user_defaults_on_insert(session):
    u = User(email="new@example.com", password_hash="hashed-value")
    session.add(u)
    session.commit()

    fetched = session.query(User).one()
    assert fetched.is_email_verified is False
    assert fetched.is_active is True
    assert fetched.is_staff is False
    assert fetched.staff_role is None


def test_user_email_is_unique(session):
    session.add(User(email="dup@example.com", password_hash="a"))
    session.commit()

    session.add(User(email="dup@example.com", password_hash="b"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_user_staff_role_independent_of_is_staff_flag(session):
    """RBAC decision: is_staff/staff_role is orthogonal to subscription
    lifecycle -- a staff user's role is set here, nothing about
    subscription status lives on User at all."""
    admin = User(
        email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN
    )
    session.add(admin)
    session.commit()

    fetched = session.query(User).filter_by(email="admin@example.com").one()
    assert fetched.is_staff is True
    assert fetched.staff_role == StaffRole.ADMIN


def test_user_can_be_suspended_without_deletion(session, user):
    user.is_active = False
    session.commit()

    fetched = session.query(User).filter_by(id=user.id).one()
    assert fetched.is_active is False


# --- UserSession -------------------------------------------------------


def test_user_session_round_trip_and_cascade_delete(session, user):
    us = UserSession(
        user_id=user.id,
        refresh_token_jti="jti-1",
        family_id="family-1",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    session.add(us)
    session.commit()

    session.refresh(user)
    assert len(user.sessions) == 1

    session.delete(user)
    session.commit()
    assert session.query(UserSession).count() == 0


def test_user_session_refresh_token_jti_is_unique(session, user):
    session.add(
        UserSession(
            user_id=user.id, refresh_token_jti="dup-jti", family_id="f1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    session.commit()

    session.add(
        UserSession(
            user_id=user.id, refresh_token_jti="dup-jti", family_id="f2",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_user_session_revocation(session, user):
    us = UserSession(
        user_id=user.id, refresh_token_jti="jti-2", family_id="family-2",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    session.add(us)
    session.commit()

    assert us.revoked_at is None
    us.revoked_at = datetime.now(timezone.utc)
    session.commit()

    fetched = session.query(UserSession).filter_by(id=us.id).one()
    assert fetched.revoked_at is not None


# --- EmailVerificationToken / PasswordResetToken ----------------------------


def test_email_verification_token_round_trip(session, user):
    token = EmailVerificationToken(
        user_id=user.id, token_hash="hash-abc",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    session.add(token)
    session.commit()

    fetched = session.query(EmailVerificationToken).one()
    assert fetched.consumed_at is None
    assert fetched.user_id == user.id


def test_email_verification_token_hash_is_unique(session, user):
    session.add(
        EmailVerificationToken(
            user_id=user.id, token_hash="dup-hash", expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )
    )
    session.commit()

    session.add(
        EmailVerificationToken(
            user_id=user.id, token_hash="dup-hash", expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_password_reset_token_single_use_via_consumed_at(session, user):
    token = PasswordResetToken(
        user_id=user.id, token_hash="reset-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(token)
    session.commit()

    assert token.consumed_at is None
    token.consumed_at = datetime.now(timezone.utc)
    session.commit()

    fetched = session.query(PasswordResetToken).filter_by(id=token.id).one()
    assert fetched.consumed_at is not None
