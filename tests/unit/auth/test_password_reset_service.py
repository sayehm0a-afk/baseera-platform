from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import password_reset_service, session_service, user_service
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.auth.password_hashing import verify_password
from src.auth.repository import AuthRepository
from src.auth.token_hashing import hash_token
from src.core.db.database import Base


def is_redis_available() -> bool:
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not is_redis_available(), reason="Redis not available")


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
def verified_user(session):
    repo = AuthRepository()
    user_service.register(session, "reset-me@example.com", "old-password")
    user = repo.get_user_by_email(session, "reset-me@example.com")
    repo.set_email_verified(session, user.id)
    return user


def _issue_and_capture_reset_token(session, user) -> str:
    with patch("src.auth.password_reset_service.get_email_sender") as mock_sender:
        password_reset_service.issue_reset_token(session, user)
        raw_token = mock_sender.return_value.send_password_reset_email.call_args[0][1]
    return raw_token


def test_reset_password_changes_the_password_hash(session, verified_user):
    raw_token = _issue_and_capture_reset_token(session, verified_user)
    password_reset_service.reset_password(session, raw_token, "new-password")

    updated = AuthRepository().get_user_by_id(session, verified_user.id)
    assert verify_password("new-password", updated.password_hash) is True
    assert verify_password("old-password", updated.password_hash) is False


def test_reset_password_sends_a_security_alert_email(session, verified_user):
    raw_token = _issue_and_capture_reset_token(session, verified_user)

    with patch("src.auth.password_reset_service.get_email_sender") as mock_sender:
        password_reset_service.reset_password(session, raw_token, "new-password")
        mock_sender.return_value.send_security_alert_email.assert_called_once()
        assert mock_sender.return_value.send_security_alert_email.call_args[0][0] == "reset-me@example.com"


def test_reset_password_rejects_unknown_token(session):
    with pytest.raises(InvalidOrExpiredTokenError):
        password_reset_service.reset_password(session, "not-a-real-token", "new-password")


def test_reset_password_rejects_already_consumed_token(session, verified_user):
    raw_token = _issue_and_capture_reset_token(session, verified_user)
    password_reset_service.reset_password(session, raw_token, "new-password")

    with pytest.raises(InvalidOrExpiredTokenError):
        password_reset_service.reset_password(session, raw_token, "another-password")


def test_reset_password_rejects_expired_token(session, verified_user):
    raw_token = _issue_and_capture_reset_token(session, verified_user)
    repo = AuthRepository()
    token_row = repo.get_password_reset_token_by_hash(session, hash_token(raw_token))
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.commit()

    with pytest.raises(InvalidOrExpiredTokenError):
        password_reset_service.reset_password(session, raw_token, "new-password")


def test_reset_password_revokes_all_existing_sessions(session, verified_user):
    pair = session_service.create_session(session, verified_user)
    raw_token = _issue_and_capture_reset_token(session, verified_user)

    password_reset_service.reset_password(session, raw_token, "new-password")

    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, pair.refresh_token)
