"""API-layer configuration, read from environment variables at call
time (never at import time -- the same lazy-init discipline
src.core.db.database's engine already established at M0, so importing
this module has no side effects and nothing needs a real environment
to be importable in tests).

Reuses SECRET_KEY/API_KEY, both already present as placeholders in
.env.example before this milestone; adds the handful of auth-foundation
settings this milestone actually needs, documented there.
"""

import os

# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

_DEFAULT_ACCESS_TOKEN_EXPIRE_SECONDS = 15 * 60  # 15 minutes
_DEFAULT_REFRESH_TOKEN_EXPIRE_SECONDS = 7 * 24 * 60 * 60  # 7 days


def get_jwt_secret() -> str:
    return os.getenv("SECRET_KEY", "")


def get_access_token_expire_seconds() -> int:
    return int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_SECONDS", _DEFAULT_ACCESS_TOKEN_EXPIRE_SECONDS))


def get_refresh_token_expire_seconds() -> int:
    return int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_SECONDS", _DEFAULT_REFRESH_TOKEN_EXPIRE_SECONDS))


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def get_configured_api_key() -> str:
    return os.getenv("API_KEY", "")


# ---------------------------------------------------------------------------
# The single foundation admin account (see src/api/auth/__init__.py)
# ---------------------------------------------------------------------------


def get_admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "")


def get_admin_password_hash() -> str:
    return os.getenv("ADMIN_PASSWORD_HASH", "")


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def get_cors_allowed_origins() -> list:
    """Comma-separated in CORS_ALLOWED_ORIGINS; empty (no origins
    allowed) by default -- an API with no configured frontend origin
    should not silently allow every origin."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def get_rate_limit_requests_per_window() -> int:
    return int(os.getenv("RATE_LIMIT_REQUESTS_PER_WINDOW", 60))


def get_rate_limit_window_seconds() -> int:
    return int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", 60))
