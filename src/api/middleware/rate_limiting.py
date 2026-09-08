"""Shared slowapi Limiter for the whole app, backed by Redis (not an
in-process in-memory store) so the limit budget is consistent across
multiple gunicorn worker processes in production -- an in-memory
limiter would let each worker enforce its own independent budget,
silently multiplying the effective limit by the worker count.

Strict per-route limits are applied at the brute-force/enumeration
surfaces (`/auth/login`, `/auth/register`, `/auth/refresh`,
`/auth/verify-email`, `/auth/resend-verification`,
`/auth/forgot-password`, `/auth/reset-password`) via `@limiter.limit(
..., key_func=auth_target_key)` decorators on those routes (see
`auth_target_key` below for why they override the default key_func);
everything else gets no explicit decorator, i.e. unlimited at this
layer (a lighter global default can be added later without changing
this module).
"""

import json

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from src.auth.token_hashing import hash_token
from src.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_dsn,
    enabled=settings.rate_limit_enabled,
)


def _already_parsed_json_body(request: Request) -> dict:
    """Best-effort, synchronous read of the JSON body FastAPI has
    already parsed for this request by the time a rate-limit key_func
    runs: slowapi's `@limiter.limit(...)` decorator wraps the endpoint
    callable itself, so its check always executes after FastAPI's own
    dependency resolution -- including parsing the route's Pydantic
    body parameter -- has completed. That resolution reads the request
    body via Starlette's `Request.body()`, which caches the raw bytes
    on `request._body` the first time (see starlette.requests.Request)
    specifically so a *second* read never re-touches the ASGI receive
    channel. Reading that same cache here needs no `await` (a rate
    limit key_func is called synchronously -- see slowapi's
    `Limiter._Limiter__evaluate_limits`), and never triggers a fresh
    read of its own: on any route without a body parameter (e.g.
    `/auth/refresh`), or a body slowapi never got this far to see
    (already-rejected malformed JSON never reaches a decorated
    endpoint), this simply finds nothing cached and returns `{}`.
    """
    body = getattr(request, "_body", None)
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def auth_target_key(request: Request) -> str:
    """Rate-limit key for the auth brute-force/enumeration surfaces:
    keyed on the ACCOUNT OR TOKEN a request targets, never on network
    address alone.

    The frontend now proxies every browser request through its own
    Next.js server (see docs/governance/ADR-safari-session-recovery.md)
    so that Safari's third-party-cookie policy doesn't break sessions.
    That means `get_remote_address()` -- `request.client.host` -- sees
    the *frontend's own* address for every real visitor once deployed,
    which would collapse every distinct user's login/register/refresh
    budget into one shared bucket. The fix is not to trust a network
    header instead (`X-Forwarded-For` is never read anywhere in this
    function, or anywhere else in this codebase's rate limiting --
    it is trivially forgeable by anyone who can reach this route
    directly, proxied or not); it is to key on something a network
    hop cannot change: the specific account or token this exact
    request is already trying to authenticate, verify, or reset --
    already validated as well-formed by this same request's Pydantic
    body (or its `refresh_token` cookie) before any handler runs.

    This keeps every limit's configured value exactly as strict as
    before per account/token (login/register/refresh protection is
    unchanged, not weakened), while making two different accounts'
    budgets fully independent of each other and of how many network
    hops either request passed through -- including two requests that
    happen to share the same source address (e.g. two different
    Next.js-proxied users, or two legitimate devices on one NAT).

    Falls back to `get_remote_address()` only when no identity is
    present at all (a route reusing this key_func without a matching
    body/cookie shape) -- never a weaker key than before, just a
    better one when an identity is available."""
    body = _already_parsed_json_body(request)

    email = body.get("email")
    if isinstance(email, str) and email.strip():
        return f"acct:{email.strip().lower()}"

    token = body.get("token")
    if isinstance(token, str) and token:
        return f"tok:{hash_token(token)}"

    refresh_cookie = request.cookies.get("refresh_token")
    if refresh_cookie:
        return f"tok:{hash_token(refresh_cookie)}"

    return f"net:{get_remote_address(request)}"
