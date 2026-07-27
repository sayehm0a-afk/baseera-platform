"""CSRFMiddleware: double-submit cookie verification for mutating
/api/v1/* requests made with an existing cookie-based session.

Only applies when the request already carries an `access_token` or
`refresh_token` cookie -- a request with neither has no ambient
authority a forged cross-site request could hijack in the first place
(this is exactly how /register and /login stay unaffected: neither
cookie exists yet on that first request). Once a session exists,
every non-GET/HEAD/OPTIONS request to /api/v1/* must echo the
non-httpOnly `csrf_token` cookie (set alongside the session cookies at
login/refresh -- see src/api/routes/auth.py) back as an `X-CSRF-Token`
header; only same-origin JavaScript (which a cross-site attacker's
forged form cannot run) can read that cookie to construct the header,
which is the entire point of the double-submit pattern.
"""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "x-csrf-token"


def _has_session_cookie(request: Request) -> bool:
    return "access_token" in request.cookies or "refresh_token" in request.cookies


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            request.method not in _SAFE_METHODS
            and request.url.path.startswith("/api/v1/")
            and _has_session_cookie(request)
        ):
            cookie_value = request.cookies.get(_CSRF_COOKIE)
            header_value = request.headers.get(_CSRF_HEADER)
            if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "csrf_verification_failed", "message": "Missing or invalid CSRF token."}},
                )

        return await call_next(request)
