"""Issues and consumes password-reset tokens. Completing a reset also
revokes every active session for the account ("sign out everywhere") --
a password reset is frequently a response to a suspected compromise, so
any session established under the old password should not survive it.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.auth import session_service
from src.auth.email_sender import get_email_sender
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.auth.password_hashing import hash_password
from src.auth.repository import AuthRepository
from src.auth.token_hashing import generate_token, hash_token
from src.core.config import settings
from src.domain.models import User

_repository = AuthRepository()


def issue_reset_token(session: Session, user: User) -> None:
    raw_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.password_reset_token_expire_hours)
    _repository.create_password_reset_token(session, user.id, hash_token(raw_token), expires_at)
    get_email_sender().send_password_reset_email(user.email, raw_token)


def reset_password(session: Session, raw_token: str, new_password: str) -> User:
    token = _repository.get_password_reset_token_by_hash(session, hash_token(raw_token))
    if token is None:
        raise InvalidOrExpiredTokenError("Password reset token is invalid.")
    if token.consumed_at is not None:
        raise InvalidOrExpiredTokenError("Password reset token has already been used.")

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise InvalidOrExpiredTokenError("Password reset token has expired.")

    _repository.consume_password_reset_token(session, token.id)
    _repository.set_password_hash(session, token.user_id, hash_password(new_password))
    session_service.revoke_all_sessions(session, token.user_id)

    user = _repository.get_user_by_id(session, token.user_id)
    get_email_sender().send_security_alert_email(
        user.email, "تم تغيير كلمة مرور حسابك في بصيرة AI، وتم تسجيل خروجك من جميع الأجهزة كإجراء احترازي."
    )
    return user
