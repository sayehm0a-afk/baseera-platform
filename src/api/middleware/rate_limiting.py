"""Shared slowapi Limiter for the whole app, backed by Redis (not an
in-process in-memory store) so the limit budget is consistent across
multiple gunicorn worker processes in production -- an in-memory
limiter would let each worker enforce its own independent budget,
silently multiplying the effective limit by the worker count.

Strict per-route limits are applied at the brute-force/enumeration
surfaces (`/auth/login`, `/auth/register`, `/auth/refresh`,
`/auth/verify-email`, `/auth/resend-verification`,
`/auth/forgot-password`, `/auth/reset-password`) via TWO independent,
both-must-pass checks on each of those seven routes: `@limiter.limit(
..., key_func=auth_target_key)` (per-account/token -- see
`auth_target_key`) AND `Depends(enforce_network_ceiling(...))`
(per-network-address -- see `enforce_network_ceiling`). Everything
else gets no explicit decorator, i.e. unlimited at this layer (a
lighter global default can be added later without changing this
module).
"""

import json

from limits import parse as parse_rate_limit
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.wrappers import Limit as SlowapiLimit
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


def enforce_network_ceiling(scope: str, limit_value: str):
    """FastAPI dependency factory: an INDEPENDENT, unspoofable,
    per-network-address ceiling -- run this ALONGSIDE (never instead
    of) `auth_target_key`'s per-account/token limit on the same route,
    as a second, both-must-pass gate rather than merged into one key.

    `auth_target_key` alone has a real gap: it lets an attacker refill
    its own budget for free by presenting a different identity on
    every single request. That identity is never checked against a
    real record before this point -- Pydantic only validates that
    `email` looks like an email and `token` is a non-empty string --
    so /register can be hit with a fresh never-used address every
    time, and /verify-email, /reset-password, /refresh (keyed on a
    hash of whatever token or `refresh_token` cookie value was
    presented) can be hit with a freshly made-up value every time:
    each one hashes to a bucket nobody has ever touched, so the
    per-account/token check alone never fires for that attack shape.

    This restores exactly the ORIGINAL, network-address-keyed ceiling
    this route had before `auth_target_key` existed: `get_remote_address`
    -- the same `request.client.host` ASGI transport peer this
    codebase already trusts everywhere else (session.py, audit_log.py,
    the admin session list), backed by Redis via the same shared
    `limiter` this module already configures. Never `X-Forwarded-For`
    or any other client-suppliable header -- nothing here becomes
    trustworthy just because it claims to be a proxy's own address;
    the ASGI transport's own peer is the one thing a request's sender
    cannot simply declare a different value for. Identity-cycling
    alone can therefore no longer produce unlimited attempts: varying
    the email or token no longer resets this second gate, which counts
    by the real, unspoofable connection instead.

    Trade-off, disclosed rather than hidden: once real traffic reaches
    this route through the frontend's own Next.js proxy (see
    docs/governance/ADR-safari-session-recovery.md), every real
    visitor's request arrives from the *same* address (the frontend's
    own), so in production this ceiling is a site-wide aggregate for
    this one route, not a per-visitor limit -- exactly the same
    characteristic this route already had before `auth_target_key` was
    introduced, at the exact same configured value, restored as a
    second layer rather than raised or invented. That is deliberate:
    this function must never be used to quietly raise a limit to "feel
    safer" -- callers pass the same `limit_value` the route already
    uses for `auth_target_key`.

    Raises the real `slowapi.errors.RateLimitExceeded` (not a bare
    `HTTPException`) so a request blocked by this gate gets the exact
    same 429 envelope shape as one blocked by `auth_target_key` --
    `main.py`'s existing `RateLimitExceeded` handler is the only thing
    that ever formats either. That handler always reads
    `request.state.view_rate_limit` for header injection (a no-op
    while `headers_enabled` stays at this `Limiter`'s default `False`,
    but still an unconditional attribute read) -- FastAPI resolves this
    dependency before ever calling the endpoint slowapi's own decorator
    wraps, so that attribute would not exist yet without setting it
    here first."""
    limit_item = parse_rate_limit(limit_value)
    wrapped_limit = SlowapiLimit(
        limit=limit_item,
        key_func=get_remote_address,
        scope=scope,
        per_method=False,
        methods=None,
        error_message=None,
        exempt_when=None,
        cost=1,
        override_defaults=True,
    )

    def _dependency(request: Request) -> None:
        if not limiter.enabled:
            return
        network_key = get_remote_address(request)
        if not limiter.limiter.hit(limit_item, "auth-network-ceiling", scope, network_key):
            request.state.view_rate_limit = None
            raise RateLimitExceeded(wrapped_limit)

    return _dependency
