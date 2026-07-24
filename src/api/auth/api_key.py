"""API key verification against the single configured service key
(`API_KEY` in .env.example, already present as a placeholder since
before this milestone). A real multi-key store (per-client keys, scoped
permissions, rotation, revocation) is out of scope for this foundation
-- see this package's `__init__.py`.
"""

import hmac
from typing import Optional


def verify_api_key(presented_key: Optional[str], configured_key: Optional[str]) -> bool:
    """Constant-time comparison. False if either side is empty/unset --
    an unconfigured API_KEY must never accidentally accept an empty
    presented key as a match."""
    if not presented_key or not configured_key:
        return False
    return hmac.compare_digest(presented_key, configured_key)
