"""UserService: the one place registration/login business rules live --
mirrors the "business rules in one service, persistence in one
repository" split every other package in this codebase already uses
(e.g. PortfolioEngine vs. PortfolioRepository).
"""

from sqlalchemy.orm import Session

from src.auth import email_verification_service
from src.auth.exceptions import (
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
)
from src.auth.password_hashing import hash_password, verify_password
from src.auth.repository import AuthRepository
from src.core.monitoring.prometheus_metrics import get_metrics
from src.domain.models import User
from src.subscriptions import subscription_service

_repository = AuthRepository()


def register(session: Session, email: str, password: str, full_name: "str | None" = None) -> User:
    normalized_email = email.strip().lower()
    if _repository.get_user_by_email(session, normalized_email) is not None:
        raise EmailAlreadyRegisteredError(f"An account with email {normalized_email!r} already exists.")

    user = _repository.create_user(session, normalized_email, hash_password(password), full_name)
    email_verification_service.issue_verification_token(session, user)
    subscription_service.provision_trial_subscription(session, user)
    get_metrics().record_registration()
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    user = _repository.get_user_by_email(session, normalized_email)

    if user is None or not verify_password(password, user.password_hash):
        get_metrics().record_login("failure")
        raise InvalidCredentialsError("Email or password is incorrect.")

    if not user.is_active:
        get_metrics().record_login("failure")
        raise AccountSuspendedError("This account has been suspended.")

    if not user.is_email_verified:
        get_metrics().record_login("failure")
        raise EmailNotVerifiedError("Please verify your email address before signing in.")

    _repository.record_login(session, user.id)
    get_metrics().record_login("success")
    return user
