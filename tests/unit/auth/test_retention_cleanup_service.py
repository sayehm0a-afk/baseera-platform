"""Phase 13 P13.6: RetentionCleanupService -- proves each cleanup pass
only removes genuinely stale rows (never anything still meaningfully
"live"), and that running the whole cleanup twice in a row is
idempotent (the second run deletes nothing further)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import retention_cleanup_service
from src.auth.repository import AuthRepository
from src.core.db.database import Base
from src.domain.models import EmailVerificationToken, PasswordResetToken, User, UserSession


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
    u = User(email="retention@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


def _now():
    return datetime.now(timezone.utc)


def test_deletes_a_session_revoked_long_ago(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "session_retention_days", 30)
    old = _now() - timedelta(days=60)
    session.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti="jti-old",
            family_id="fam-old",
            expires_at=old + timedelta(days=30),
            revoked_at=old,
        )
    )
    session.commit()

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.sessions_deleted == 1
    assert session.query(UserSession).count() == 0


def test_keeps_a_recently_revoked_session(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "session_retention_days", 30)
    recent = _now() - timedelta(days=1)
    session.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti="jti-recent",
            family_id="fam-recent",
            expires_at=recent + timedelta(days=30),
            revoked_at=recent,
        )
    )
    session.commit()

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.sessions_deleted == 0
    assert session.query(UserSession).count() == 1


def test_keeps_a_still_active_session(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "session_retention_days", 30)
    session.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti="jti-active",
            family_id="fam-active",
            expires_at=_now() + timedelta(days=30),
        )
    )
    session.commit()

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.sessions_deleted == 0
    assert session.query(UserSession).count() == 1


def test_deletes_a_session_that_quietly_expired_and_was_never_revoked(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "session_retention_days", 30)
    session.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti="jti-quiet",
            family_id="fam-quiet",
            expires_at=_now() - timedelta(days=60),
        )
    )
    session.commit()

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.sessions_deleted == 1


def test_deletes_expired_email_verification_tokens_whether_consumed_or_not(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "token_retention_days", 7)
    repo = AuthRepository()
    old = _now() - timedelta(days=30)
    repo.create_email_verification_token(session, user.id, "hash-unconsumed", old)
    consumed = repo.create_email_verification_token(session, user.id, "hash-consumed", old)
    repo.consume_email_verification_token(session, consumed.id)

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.email_verification_tokens_deleted == 2
    assert session.query(EmailVerificationToken).count() == 0


def test_keeps_a_still_valid_email_verification_token(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "token_retention_days", 7)
    repo = AuthRepository()
    repo.create_email_verification_token(session, user.id, "hash-valid", _now() + timedelta(hours=1))

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.email_verification_tokens_deleted == 0
    assert session.query(EmailVerificationToken).count() == 1


def test_deletes_expired_password_reset_tokens(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "token_retention_days", 7)
    repo = AuthRepository()
    old = _now() - timedelta(days=30)
    repo.create_password_reset_token(session, user.id, "hash-old-reset", old)

    summary = retention_cleanup_service.run_retention_cleanup(session)

    assert summary.password_reset_tokens_deleted == 1
    assert session.query(PasswordResetToken).count() == 0


def test_running_cleanup_twice_in_a_row_is_idempotent(session, user, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "token_retention_days", 7)
    repo = AuthRepository()
    old = _now() - timedelta(days=60)
    session.add(
        UserSession(
            user_id=user.id, refresh_token_jti="jti-a", family_id="fam-a",
            expires_at=old + timedelta(days=30), revoked_at=old,
        )
    )
    repo.create_email_verification_token(session, user.id, "hash-a", old)
    repo.create_password_reset_token(session, user.id, "hash-b", old)
    session.commit()

    first = retention_cleanup_service.run_retention_cleanup(session)
    second = retention_cleanup_service.run_retention_cleanup(session)

    assert first.total_deleted == 3
    assert second.total_deleted == 0
