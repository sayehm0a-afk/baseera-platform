"""POST /api/v1/bootstrap/owner -- a temporary, self-disabling escape
hatch for creating the very first OWNER account on a deployment that
has none yet, when the operator has no direct database access to run
scripts/bootstrap_owner.py (the normal, preferred path -- see that
script's docstring; it is deliberately never exposed over HTTP).

This route exists ONLY because that normal path was unreachable in a
specific real situation: no Railway CLI/SSH access, no public database
proxy, and the project's Railway API token doesn't support SSH key
management. It is meant to be added, used exactly once, and then
deleted from the codebase entirely -- not a permanent feature.

Threat model / why this is safe to expose, despite being unauthenticated:
  1. Gated by BOOTSTRAP_TOKEN, a high-entropy secret that exists only
     as a Railway environment variable (never committed, never
     logged). Compared with `hmac.compare_digest` (constant-time, no
     partial-match timing signal). If BOOTSTRAP_TOKEN is unset, no
     value the caller sends can ever match -- the route silently
     behaves as if disabled with no separate "not configured" branch
     to leak that distinction.
  2. Self-disabling by real database state, not an in-memory or
     config flag: `bootstrap_first_owner` refuses the moment any
     OWNER account exists, forever, surviving restarts/redeploys.
     Checked only *after* the token already matched, so a caller
     without the token learns nothing about whether bootstrap has
     already happened.
  3. Atomic: the zero-owner check and the insert happen in one
     PostgreSQL transaction under a transaction-scoped advisory lock
     (src/auth/bootstrap_service.py), so two concurrent requests can't
     both create "the first" OWNER.
  4. Rate-limited (defense in depth against token brute-forcing,
     though the primary defense is the token's entropy).
  5. Never logs the token or password; the response never echoes the
     password back.
"""

import hmac

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.middleware.rate_limiting import limiter
from src.api.schemas.auth import BootstrapOwnerRequest, UserOut
from src.auth.bootstrap_service import bootstrap_first_owner
from src.auth.exceptions import InvalidCredentialsError
from src.core.config import settings
from src.core.db.database import get_db

router = APIRouter(prefix="/api/v1/bootstrap", tags=["bootstrap"])


@router.post("/owner", response_model=UserOut, status_code=201)
@limiter.limit("5/hour")
def create_first_owner(
    request: Request,
    body: BootstrapOwnerRequest,
    session: Session = Depends(get_db),
) -> UserOut:
    provided_token = request.headers.get("x-bootstrap-token", "")
    configured_token = settings.bootstrap_token or ""
    # Constant-time compare against a real token; an unset
    # BOOTSTRAP_TOKEN compares against "" (never equal to any
    # non-empty header a caller could send), so this one check also
    # covers "route not configured" with no separate code path.
    if not configured_token or not hmac.compare_digest(provided_token, configured_token):
        raise InvalidCredentialsError("Invalid or missing bootstrap token.")

    user = bootstrap_first_owner(session, body.email, body.password)
    return UserOut.model_validate(user)
