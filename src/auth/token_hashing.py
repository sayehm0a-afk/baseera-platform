"""Shared helper for every bearer-token type this package issues (email
verification, password reset, refresh tokens): generate a high-entropy
random value to hand to the client, but only ever persist a hash of it --
the same "a DB leak shouldn't hand out live credentials" discipline this
codebase already applies to password hashes.

Not reversible (unlike, say, an HMAC scheme) -- verifying a presented
token means re-hashing it and comparing against the stored hash, so
there is nothing to steal from a leaked token_hash column.
"""

import hashlib
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
