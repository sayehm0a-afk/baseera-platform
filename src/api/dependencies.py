"""FastAPI dependencies for the API layer.

The DB session dependency is NOT redefined here -- src.core.db.database
already exposes get_db() as a FastAPI-style generator dependency
(sync Session, matching every existing DB-touching module in this
codebase); routes import that directly. This module only adds the two
provider dependencies, which need to be async (provider selection
involves an awaited connectivity probe -- see
src.market_data.provider_factory), plus get_current_user, the one
dependency every authenticated route depends on.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from src.auth import token_store
from src.auth.exceptions import UnauthenticatedError
from src.auth.jwt_service import InvalidAccessTokenError, decode_access_token
from src.auth.repository import AuthRepository
from src.core.db.database import get_db
from src.domain.models import User
from src.market_data.fundamental_provider_factory import get_fundamental_data_provider
from src.market_data.provider_factory import get_market_data_provider
from src.market_data.providers.fundamental_data_provider import IFundamentalDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider

_auth_repository = AuthRepository()


async def get_market_provider() -> IMarketDataProvider:
    return await get_market_data_provider()


async def get_fundamental_provider() -> IFundamentalDataProvider:
    return await get_fundamental_data_provider()


def get_current_user(
    access_token: Optional[str] = Cookie(default=None),
    session: Session = Depends(get_db),
) -> User:
    """Reads the httpOnly `access_token` cookie (never an Authorization
    header -- see Phase 10 plan decision 3), verifies its signature and
    expiry, and checks the short-lived Redis revocation set for the
    rare case it was explicitly revoked (logout, admin suspend) before
    its own expiry. Every authenticated route depends on this."""
    if not access_token:
        raise UnauthenticatedError("No access token was presented.")

    try:
        claims = decode_access_token(access_token)
    except InvalidAccessTokenError as exc:
        raise UnauthenticatedError(str(exc)) from exc

    if token_store.is_access_token_revoked(claims["jti"]):
        raise UnauthenticatedError("Access token has been revoked.")

    user = _auth_repository.get_user_by_id(session, int(claims["sub"]))
    if user is None or not user.is_active:
        raise UnauthenticatedError("Account no longer exists or is inactive.")

    if user.tokens_invalid_before is not None:
        invalid_before = user.tokens_invalid_before
        if invalid_before.tzinfo is None:
            invalid_before = invalid_before.replace(tzinfo=timezone.utc)
        issued_at = datetime.fromtimestamp(claims["iat"], tz=timezone.utc)
        if issued_at < invalid_before:
            raise UnauthenticatedError("Access token was issued before a full session revocation.")

    return user
