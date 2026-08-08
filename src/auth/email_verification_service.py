"""Issues and verifies the email-verification token every new
registration needs before it can log in (decision: email verification
is required before login on a financial platform, not merely gating
premium features).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.auth.email_sender import get_email_sender
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.auth.repository import AuthRepository
from src.auth.token_hashing import generate_token, hash_token
from src.core.config import settings
from src.domain.models import User

_repository = AuthRepository()


def issue_verification_token(session: Session, user: User) -> None:
    """Also used by the /resend-verification route to reissue a fresh
    token for an already-registered, not-yet-verified account -- that
    route is responsible for the enumeration-safe generic response and
    for only calling this when `not user.is_email_verified`."""
    raw_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_token_expire_hours)
    _repository.create_email_verification_token(session, user.id, hash_token(raw_token), expires_at)
    get_email_sender().send_verification_email(user.email, raw_token)


def verify_email(session: Session, raw_token: str) -> User:
    token = _repository.get_email_verification_token_by_hash(session, hash_token(raw_token))
    if token is None:
        raise InvalidOrExpiredTokenError("Verification token is invalid.")
    if token.consumed_at is not None:
        raise InvalidOrExpiredTokenError("Verification token has already been used.")

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise InvalidOrExpiredTokenError("Verification token has expired.")

    _repository.consume_email_verification_token(session, token.id)
    _repository.set_email_verified(session, token.user_id)

    user = _repository.get_user_by_id(session, token.user_id)
    get_email_sender().send_welcome_email(user.email, user.full_name)
    return user
