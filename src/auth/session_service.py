"""SessionService: issues, rotates, and revokes login sessions.

Refresh-token rotation with reuse detection: every successful
`refresh()` call issues a brand-new refresh token in the same `family_id`
and immediately revokes the one just presented. If a refresh token is
presented that has *already* been revoked (i.e. it was already rotated
away once), that's a strong signal it was stolen and used out of band --
the entire family (every session descended from that original login) is
revoked, forcing a fresh login everywhere. This is the standard defense
against a leaked refresh token being replayed after the legitimate
client has already rotated past it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.auth import jwt_service, token_store
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.auth.repository import AuthRepository
from src.auth.token_hashing import generate_token, hash_token
from src.core.config import settings
from src.domain.models import User, UserSession

_repository = AuthRepository()


@dataclass(frozen=True)
class SessionPair:
    access_token: str
    refresh_token: str  # raw value -- set as the httpOnly refresh cookie, never persisted as-is


def _refresh_ttl_seconds() -> int:
    return settings.refresh_token_expire_days * 24 * 60 * 60


def _issue_refresh_token(
    session: Session, user: User, family_id: str, device_label: Optional[str], ip_address: Optional[str]
) -> str:
    raw_token = generate_token()
    jti = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    _repository.create_user_session(
        session,
        user_id=user.id,
        refresh_token_jti=jti,
        family_id=family_id,
        expires_at=expires_at,
        device_label=device_label,
        ip_address=ip_address,
    )
    token_store.store_refresh_session(jti, user.id, _refresh_ttl_seconds())
    return raw_token


def create_session(
    session: Session, user: User, device_label: Optional[str] = None, ip_address: Optional[str] = None
) -> SessionPair:
    family_id = uuid.uuid4().hex
    raw_refresh = _issue_refresh_token(session, user, family_id, device_label, ip_address)
    access_token = jwt_service.encode_access_token(
        user.id, user.is_staff, user.staff_role.value if user.staff_role else None
    )
    return SessionPair(access_token=access_token, refresh_token=raw_refresh)


def refresh_session(session: Session, raw_refresh_token: str) -> SessionPair:
    jti = hash_token(raw_refresh_token)
    user_session = _repository.get_user_session_by_jti(session, jti)

    if user_session is None:
        raise InvalidOrExpiredTokenError("Refresh token is unknown.")

    if user_session.revoked_at is not None:
        # Reuse of an already-rotated-away token -- treat the whole
        # family as compromised.
        _repository.revoke_session_family(session, user_session.family_id)
        raise InvalidOrExpiredTokenError(
            "This refresh token has already been used. All sessions from this login have been revoked."
        )

    now = datetime.now(timezone.utc)
    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise InvalidOrExpiredTokenError("Refresh token has expired.")

    user = _repository.get_user_by_id(session, user_session.user_id)
    if user is None or not user.is_active:
        raise InvalidOrExpiredTokenError("Account is no longer active.")

    # Rotate: revoke the presented token, issue a new one in the same family.
    _repository.revoke_user_session(session, user_session.id)
    token_store.delete_refresh_session(jti)

    raw_refresh = _issue_refresh_token(
        session, user, user_session.family_id, user_session.device_label, user_session.ip_address
    )
    access_token = jwt_service.encode_access_token(
        user.id, user.is_staff, user.staff_role.value if user.staff_role else None
    )
    return SessionPair(access_token=access_token, refresh_token=raw_refresh)


def revoke_session(session: Session, raw_refresh_token: str) -> None:
    """Single-device logout."""
    jti = hash_token(raw_refresh_token)
    user_session = _repository.get_user_session_by_jti(session, jti)
    if user_session is not None:
        _repository.revoke_user_session(session, user_session.id)
        token_store.delete_refresh_session(jti)


def revoke_all_sessions(session: Session, user_id: int) -> None:
    """"Sign out everywhere" -- also used internally after a password
    reset completes. Also instantly invalidates any access token
    already issued to this user (see User.tokens_invalid_before) --
    without this, a still-unexpired access token would keep working
    for up to its remaining 15-minute lifetime despite every session
    having just been revoked, defeating the point of "sign out
    everywhere" as an incident response to a suspected compromise."""
    sessions = _repository.list_active_sessions_for_user(session, user_id)
    _repository.revoke_all_sessions_for_user(session, user_id)
    for user_session in sessions:
        token_store.delete_refresh_session(user_session.refresh_token_jti)
    _repository.invalidate_all_access_tokens(session, user_id)


def list_sessions(session: Session, user_id: int) -> List[UserSession]:
    return _repository.list_active_sessions_for_user(session, user_id)
