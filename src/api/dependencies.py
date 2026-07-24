"""Shared FastAPI dependencies for the API layer: the database session,
symbol-to-Stock lookup (used by every analysis/market-data route, so
the 404-on-unknown-symbol behavior is defined once, not duplicated per
route), and authentication.
"""

from typing import Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from src.api import config
from src.api.auth.api_key import verify_api_key
from src.api.auth.jwt_handler import subject_from_access_token
from src.api.exceptions import NotFoundError, UnauthorizedError
from src.core.db.database import get_db
from src.domain.models import Stock

__all__ = ["get_db", "get_stock_or_404", "get_current_principal"]


def get_stock_or_404(symbol: str, db: Session = Depends(get_db)) -> Stock:
    stock = db.query(Stock).filter(Stock.symbol == symbol).one_or_none()
    if stock is None:
        raise NotFoundError(f"Stock '{symbol}' not found")
    return stock


def get_current_principal(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> str:
    """Accepts either a `Authorization: Bearer <access token>` header or
    an `X-API-Key` header -- either is sufficient (matching Priority 3's
    "JWT Authentication ... API Keys" as two independent, equally-valid
    credential mechanisms, not a requirement for both). Returns an
    opaque principal identifier string ("user:<sub>" or "api-key") for
    routes that only need to know *that* the caller is authenticated,
    not any further identity detail this foundation doesn't model yet.
    """
    if authorization is not None and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer "):].strip()
        subject = subject_from_access_token(token, config.get_jwt_secret())
        if subject is not None:
            return f"user:{subject}"

    if verify_api_key(x_api_key, config.get_configured_api_key()):
        return "api-key"

    raise UnauthorizedError("Not authenticated: provide a valid Bearer token or X-API-Key header")
