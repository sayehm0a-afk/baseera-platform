from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import email_verification_service
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.auth.repository import AuthRepository
from src.auth.token_hashing import hash_token
from src.core.db.database import Base


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
    return AuthRepository().create_user(session, "verify@example.com", "hashed")


def _issue_and_capture_token(session, user) -> str:
    with patch("src.auth.email_verification_service.get_email_sender") as mock_sender:
        email_verification_service.issue_verification_token(session, user)
        raw_token = mock_sender.return_value.send_verification_email.call_args[0][1]
    return raw_token


def test_verify_email_marks_user_verified(session, user):
    raw_token = _issue_and_capture_token(session, user)
    assert user.is_email_verified is False

    verified_user = email_verification_service.verify_email(session, raw_token)
    assert verified_user.is_email_verified is True


def test_verify_email_rejects_unknown_token(session):
    with pytest.raises(InvalidOrExpiredTokenError):
        email_verification_service.verify_email(session, "not-a-real-token")


def test_verify_email_rejects_already_consumed_token(session, user):
    raw_token = _issue_and_capture_token(session, user)
    email_verification_service.verify_email(session, raw_token)

    with pytest.raises(InvalidOrExpiredTokenError):
        email_verification_service.verify_email(session, raw_token)


def test_verify_email_rejects_expired_token(session, user):
    raw_token = _issue_and_capture_token(session, user)
    repo = AuthRepository()
    token_row = repo.get_email_verification_token_by_hash(session, hash_token(raw_token))
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.commit()

    with pytest.raises(InvalidOrExpiredTokenError):
        email_verification_service.verify_email(session, raw_token)
