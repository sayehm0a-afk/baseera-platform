"""SecurityHeadersMiddleware: a conservative baseline of response
headers on every request. This is primarily an API (not a
browser-rendered app), so the main real attack surface these headers
guard is /docs (Swagger UI) and any HTML error page a client might
render -- but they cost nothing to apply everywhere and are standard
practice regardless.

HSTS is prod-only: it tells a browser to remember "always use HTTPS
for this host" for a long time, which is actively harmful in local
dev (a developer hitting plain http://localhost would get silently
upgraded and confused) and meaningless unless the deployment actually
terminates TLS, which only production does.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.config import settings

_CSP = "default-src 'self'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
