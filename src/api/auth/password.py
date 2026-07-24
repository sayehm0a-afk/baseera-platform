"""Password hashing for the single configured admin account this
authentication foundation supports (see this package's `__init__.py`
for why there is no multi-user table yet).

PBKDF2-HMAC-SHA256 (RFC 8018), standard-library only (`hashlib.pbkdf2_hmac`
is a real, non-placeholder key-derivation function -- not a bare hash),
at 600,000 iterations (OWASP's 2023 password-storage cheat-sheet
recommendation for PBKDF2-SHA256 at time of writing).

======================================================================
ARCHITECTURAL DECISION: one fixed, application-wide salt, not a
per-user random salt -- and why that is a disclosed, scope-bound
simplification, not a general password-hashing recommendation
======================================================================
A per-user random salt exists specifically to stop one attacker's
precomputed rainbow table from cracking *every* account in a multi-user
table at once. This foundation supports exactly one configured account
(there is no user table for a rainbow table to target across), so a
single salt derived from `SECRET_KEY` does not weaken anything for the
scope this module actually serves. This is not a pattern to copy
forward once a real multi-user model exists -- that will need a random
salt stored per user record, not this module's approach.
"""

import hashlib
import hmac

_ITERATIONS = 600_000
_SALT_INFO = b"basirah-admin-password-v1"  # domain-separates this salt from any other PBKDF2 use of SECRET_KEY


def _derive(password: str, secret_key: str) -> bytes:
    salt = hashlib.sha256(secret_key.encode("utf-8") + _SALT_INFO).digest()
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)


def hash_password(password: str, secret_key: str) -> str:
    """Returns a hex-encoded digest suitable for storing in the
    ADMIN_PASSWORD_HASH environment variable (see .env.example)."""
    return _derive(password, secret_key).hex()


def verify_password(password: str, stored_hash_hex: str, secret_key: str) -> bool:
    """Constant-time comparison -- never a plain `==` on secret material."""
    if not stored_hash_hex:
        return False
    try:
        stored = bytes.fromhex(stored_hash_hex)
    except ValueError:
        return False
    candidate = _derive(password, secret_key)
    return hmac.compare_digest(candidate, stored)
