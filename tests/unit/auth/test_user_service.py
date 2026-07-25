import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import user_service
from src.auth.exceptions import (
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
)
from src.auth.repository import AuthRepository
from src.core.db.database import Base
from src.domain.models import EmailVerificationToken


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_register_creates_unverified_user(session):
    user = user_service.register(session, "New.User@Example.com", "s3cret-password")
    assert user.email == "new.user@example.com"  # normalized
    assert user.is_email_verified is False


def test_register_issues_a_verification_token(session):
    user = user_service.register(session, "verify-me@example.com", "s3cret-password")
    # Can't know the raw token (never persisted), but a row must exist.
    assert session.query(EmailVerificationToken).filter_by(user_id=user.id).count() == 1


def test_register_rejects_duplicate_email(session):
    user_service.register(session, "dup@example.com", "s3cret-password")
    with pytest.raises(EmailAlreadyRegisteredError):
        user_service.register(session, "dup@example.com", "another-password")


def test_register_email_is_case_insensitive_for_duplicates(session):
    user_service.register(session, "Case@Example.com", "s3cret-password")
    with pytest.raises(EmailAlreadyRegisteredError):
        user_service.register(session, "case@example.com", "another-password")


def test_authenticate_rejects_wrong_password(session):
    user_service.register(session, "auth1@example.com", "correct-password")
    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "auth1@example.com", "wrong-password")


def test_authenticate_rejects_unknown_email(session):
    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "nobody@example.com", "whatever")


def test_authenticate_rejects_unverified_email(session):
    user_service.register(session, "unverified@example.com", "correct-password")
    with pytest.raises(EmailNotVerifiedError):
        user_service.authenticate(session, "unverified@example.com", "correct-password")


def test_authenticate_rejects_suspended_account(session):
    repo = AuthRepository()
    user = user_service.register(session, "suspended@example.com", "correct-password")
    repo.set_email_verified(session, user.id)
    repo.set_is_active(session, user.id, False)

    with pytest.raises(AccountSuspendedError):
        user_service.authenticate(session, "suspended@example.com", "correct-password")


def test_authenticate_succeeds_when_verified_and_active(session):
    repo = AuthRepository()
    user_service.register(session, "verified@example.com", "correct-password")
    repo.set_email_verified(session, repo.get_user_by_email(session, "verified@example.com").id)

    authenticated = user_service.authenticate(session, "verified@example.com", "correct-password")
    assert authenticated.email == "verified@example.com"
    assert authenticated.last_login_at is not None
