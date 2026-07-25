"""Shared slowapi Limiter for the whole app, backed by Redis (not an
in-process in-memory store) so the limit budget is consistent across
multiple gunicorn worker processes in production -- an in-memory
limiter would let each worker enforce its own independent budget,
silently multiplying the effective limit by the worker count.

Strict per-route limits are applied at the brute-force/enumeration
surfaces (`/auth/login`, `/auth/register`, `/auth/forgot-password`) via
`@limiter.limit(...)` decorators on those routes; everything else gets
no explicit decorator, i.e. unlimited at this layer (a lighter global
default can be added later without changing this module).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"redis://{settings.redis_host}:{settings.redis_port}",
    enabled=settings.rate_limit_enabled,
)
