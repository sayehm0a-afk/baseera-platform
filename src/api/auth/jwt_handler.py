"""HS256 JSON Web Tokens (RFC 7519 claims + RFC 7515 JWS compact
serialization), implemented directly against the standard library
(`hmac`, `hashlib`, `base64`, `json`) rather than a third-party JWT
package.

======================================================================
ARCHITECTURAL DECISION: no PyJWT/python-jose dependency, by choice, not
oversight
======================================================================
Verified directly in this environment before writing this module:
`import jwt` (PyJWT) transitively imports `cryptography`, whose
`hazmat` backend in turn requires the compiled `_cffi_backend` module.
In this sandbox that chain failed with an unrecoverable Rust panic
(`pyo3_runtime.PanicException`), not a catchable `ImportError` --
meaning an app that imports PyJWT at module load time (as `main.py`
would, for an auth foundation used on every protected request) could
fail to boot entirely in an environment where `cryptography`'s native
extension is partially broken, for reasons entirely unrelated to
whether HS256 (a pure-HMAC algorithm needing no asymmetric crypto at
all) actually works. Installing `cffi` locally resolved it here, but
pinning that fix in `requirements.txt` would still leave the
application depending on a large, unrelated native-crypto dependency
tree just to compute an HMAC-SHA256 -- a real, avoidable fragility risk
for something this fundamental. HS256 is simple and well-specified
enough to implement correctly and safely against the standard library
alone, so that is what this module does. RS256/ES256 (needing real
asymmetric crypto) are out of scope here and would be a legitimate
reason to revisit this decision later.

======================================================================
Scope
======================================================================
This module only encodes/decodes/verifies tokens. It does not decide
what claims mean, does not look up users, and does not know about
`SECRET_KEY`'s source -- callers pass the secret in explicitly, kept
independent and unit-testable without environment coupling.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

_ALGORITHM = "HS256"
_HEADER = {"alg": _ALGORITHM, "typ": "JWT"}


class JWTError(Exception):
    """Raised for any invalid, malformed, expired, or signature-mismatched token."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(signing_input: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()


def encode(claims: Dict[str, Any], secret: str) -> str:
    """Encodes `claims` (expected to include "exp" for any token that
    should expire -- this function does not add one itself, callers
    decide expiry per token type, see create_access_token/
    create_refresh_token below) into a signed HS256 compact JWT.
    """
    header_b64 = _b64url_encode(json.dumps(_HEADER, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature_b64 = _b64url_encode(_sign(signing_input, secret))
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode(token: str, secret: str) -> Dict[str, Any]:
    """Verifies signature and "exp" (if present), returning the claims
    dict. Raises JWTError for any structural, signature, or expiry
    failure -- never returns a partially-trusted result.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("token does not have three dot-separated segments")

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    try:
        header = json.loads(_b64url_decode(header_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise JWTError("token header is not valid base64url-encoded JSON") from exc
    if header.get("alg") != _ALGORITHM:
        raise JWTError(f"unsupported or missing algorithm in token header: {header.get('alg')!r}")

    try:
        expected_signature = _sign(signing_input, secret)
        actual_signature = _b64url_decode(signature_b64)
    except (ValueError, UnicodeDecodeError) as exc:
        raise JWTError("token signature is not valid base64url") from exc
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise JWTError("token signature verification failed")

    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise JWTError("token payload is not valid base64url-encoded JSON") from exc

    exp = claims.get("exp")
    if exp is not None and time.time() >= float(exp):
        raise JWTError("token has expired")

    return claims


def create_access_token(subject: str, secret: str, expires_in_seconds: int) -> str:
    """`subject` identifies the principal (today: the single configured
    admin account -- see password.py). `token_type` distinguishes an
    access token from a refresh token so one can never be silently
    accepted in place of the other (create_refresh_token below sets a
    different value)."""
    now = time.time()
    return encode(
        {"sub": subject, "token_type": "access", "iat": now, "exp": now + expires_in_seconds},
        secret,
    )


def create_refresh_token(subject: str, secret: str, expires_in_seconds: int) -> str:
    now = time.time()
    return encode(
        {"sub": subject, "token_type": "refresh", "iat": now, "exp": now + expires_in_seconds},
        secret,
    )


def decode_token_of_type(token: str, secret: str, expected_type: str) -> Dict[str, Any]:
    """decode() plus the token_type check every route needs -- a
    refresh token presented where an access token is required (or vice
    versa) must be rejected, not silently accepted just because its
    signature is valid.
    """
    claims = decode(token, secret)
    if claims.get("token_type") != expected_type:
        raise JWTError(f"expected a {expected_type!r} token, got {claims.get('token_type')!r}")
    return claims


def subject_from_access_token(token: str, secret: str) -> Optional[str]:
    """Convenience used by the auth dependency: returns the subject
    claim, or None for any invalid/expired/wrong-type token -- callers
    that need to distinguish *why* verification failed should call
    decode_token_of_type directly instead."""
    try:
        claims = decode_token_of_type(token, secret, expected_type="access")
    except JWTError:
        return None
    return claims.get("sub")
