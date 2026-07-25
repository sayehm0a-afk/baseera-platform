"""Repository tests for AuthRepository -- real SQLAlchemy ORM against
an in-memory SQLite DB, no mocking of the persistence layer itself."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth.repository import AuthRepository
from src.core.db.database import Base
from src.domain.models import StaffRole


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
    return AuthRepository()


def test_create_and_get_user_by_email(session, repo):
    user = repo.create_user(session, "a@example.com", "hashed")
    fetched = repo.get_user_by_email(session, "a@example.com")
    assert fetched.id == user.id


def test_get_user_by_email_returns_none_when_missing(session, repo):
    assert repo.get_user_by_email(session, "missing@example.com") is None


def test_set_email_verified(session, repo):
    user = repo.create_user(session, "b@example.com", "hashed")
    assert user.is_email_verified is False
    repo.set_email_verified(session, user.id)
    assert repo.get_user_by_id(session, user.id).is_email_verified is True


def test_set_is_active_suspends_without_deleting(session, repo):
    user = repo.create_user(session, "c@example.com", "hashed")
    repo.set_is_active(session, user.id, False)
    fetched = repo.get_user_by_id(session, user.id)
    assert fetched.is_active is False
    assert fetched is not None


def test_invalidate_all_access_tokens_sets_the_timestamp(session, repo):
    user = repo.create_user(session, "invalidate@example.com", "hashed")
    assert repo.get_user_by_id(session, user.id).tokens_invalid_before is None

    before = datetime.now(timezone.utc)
    repo.invalidate_all_access_tokens(session, user.id)
    after = datetime.now(timezone.utc)

    fetched = repo.get_user_by_id(session, user.id)
    stamp = fetched.tokens_invalid_before
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    assert before <= stamp <= after


def test_set_staff_role(session, repo):
    user = repo.create_user(session, "d@example.com", "hashed")
    repo.set_staff_role(session, user.id, True, StaffRole.SUPPORT)
    fetched = repo.get_user_by_id(session, user.id)
    assert fetched.is_staff is True
    assert fetched.staff_role == StaffRole.SUPPORT


def test_list_users_pagination(session, repo):
    for i in range(5):
        repo.create_user(session, f"user{i}@example.com", "hashed")
    total, rows = repo.list_users(session, limit=2, offset=0)
    assert total == 5
    assert len(rows) == 2


# --- tokens -----------------------------------------------------------


def test_email_verification_token_round_trip(session, repo):
    user = repo.create_user(session, "e@example.com", "hashed")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    token = repo.create_email_verification_token(session, user.id, "hash123", expires_at)

    fetched = repo.get_email_verification_token_by_hash(session, "hash123")
    assert fetched.id == token.id
    assert fetched.consumed_at is None

    repo.consume_email_verification_token(session, token.id)
    assert repo.get_email_verification_token_by_hash(session, "hash123").consumed_at is not None


def test_password_reset_token_round_trip(session, repo):
    user = repo.create_user(session, "f@example.com", "hashed")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    token = repo.create_password_reset_token(session, user.id, "resethash", expires_at)

    fetched = repo.get_password_reset_token_by_hash(session, "resethash")
    assert fetched.id == token.id

    repo.consume_password_reset_token(session, token.id)
    assert repo.get_password_reset_token_by_hash(session, "resethash").consumed_at is not None


# --- sessions -----------------------------------------------------------


def test_create_and_get_user_session(session, repo):
    user = repo.create_user(session, "g@example.com", "hashed")
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    us = repo.create_user_session(session, user.id, "jti-1", "family-1", expires_at)

    fetched = repo.get_user_session_by_jti(session, "jti-1")
    assert fetched.id == us.id


def test_revoke_session_family(session, repo):
    user = repo.create_user(session, "h@example.com", "hashed")
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    repo.create_user_session(session, user.id, "jti-a", "family-x", expires_at)
    repo.create_user_session(session, user.id, "jti-b", "family-x", expires_at)
    repo.create_user_session(session, user.id, "jti-c", "family-y", expires_at)

    repo.revoke_session_family(session, "family-x")

    assert repo.get_user_session_by_jti(session, "jti-a").revoked_at is not None
    assert repo.get_user_session_by_jti(session, "jti-b").revoked_at is not None
    assert repo.get_user_session_by_jti(session, "jti-c").revoked_at is None


def test_revoke_all_sessions_for_user(session, repo):
    user = repo.create_user(session, "i@example.com", "hashed")
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    repo.create_user_session(session, user.id, "jti-1", "f1", expires_at)
    repo.create_user_session(session, user.id, "jti-2", "f2", expires_at)

    repo.revoke_all_sessions_for_user(session, user.id)
    assert repo.list_active_sessions_for_user(session, user.id) == []


def test_list_active_sessions_excludes_expired_and_revoked(session, repo):
    user = repo.create_user(session, "j@example.com", "hashed")
    future = datetime.now(timezone.utc) + timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(days=1)

    repo.create_user_session(session, user.id, "active", "f1", future)
    repo.create_user_session(session, user.id, "expired", "f2", past)
    revoked = repo.create_user_session(session, user.id, "revoked", "f3", future)
    repo.revoke_user_session(session, revoked.id)

    active = repo.list_active_sessions_for_user(session, user.id)
    assert [s.refresh_token_jti for s in active] == ["active"]


def test_list_all_active_sessions_for_admin(session, repo):
    user1 = repo.create_user(session, "k@example.com", "hashed")
    user2 = repo.create_user(session, "l@example.com", "hashed")
    future = datetime.now(timezone.utc) + timedelta(days=30)
    repo.create_user_session(session, user1.id, "s1", "f1", future)
    repo.create_user_session(session, user2.id, "s2", "f2", future)

    total, rows = repo.list_all_active_sessions(session, limit=10, offset=0)
    assert total == 2
    assert len(rows) == 2
