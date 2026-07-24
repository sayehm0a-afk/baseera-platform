"""Unit tests for the hand-rolled HS256 JWT implementation
(src.api.auth.jwt_handler) -- see that module's docstring for why it
does not depend on PyJWT."""

import time

import pytest

from src.api.auth.jwt_handler import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode,
    decode_token_of_type,
    encode,
    subject_from_access_token,
)

_SECRET = "test-secret-key"


def test_encode_decode_roundtrip_preserves_claims():
    token = encode({"sub": "admin", "custom": "value"}, _SECRET)
    claims = decode(token, _SECRET)
    assert claims["sub"] == "admin"
    assert claims["custom"] == "value"


def test_token_has_three_dot_separated_segments():
    token = encode({"sub": "admin"}, _SECRET)
    assert len(token.split(".")) == 3


def test_decode_rejects_tampered_signature():
    token = encode({"sub": "admin"}, _SECRET)
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-1]}x"
    with pytest.raises(JWTError, match="signature verification failed"):
        decode(tampered, _SECRET)


def test_decode_rejects_wrong_secret():
    token = encode({"sub": "admin"}, _SECRET)
    with pytest.raises(JWTError, match="signature verification failed"):
        decode(token, "a-different-secret")


def test_decode_rejects_malformed_token_structure():
    with pytest.raises(JWTError, match="three dot-separated segments"):
        decode("not-a-jwt", _SECRET)


def test_decode_rejects_malformed_header_base64():
    with pytest.raises(JWTError):
        decode("not-valid-b64!!.also-not-valid!!.signature", _SECRET)


def test_decode_rejects_malformed_signature_base64():
    # Python's base64 decoder silently ignores invalid *characters* (so a
    # string like "not-valid!!!" decodes to garbage bytes without raising,
    # only failing the later signature comparison) -- a length whose data-
    # character count is 1 more than a multiple of 4 is what actually
    # raises binascii.Error regardless of which characters are used.
    header_b64, payload_b64, _ = encode({"sub": "admin"}, _SECRET).split(".")
    forged = f"{header_b64}.{payload_b64}.A"
    with pytest.raises(JWTError, match="signature is not valid base64url"):
        decode(forged, _SECRET)


def test_decode_rejects_malformed_payload_base64_even_with_a_correct_signature():
    # A genuine HMAC over the exact bytes sent, even though the payload
    # segment itself isn't valid base64url once the signature check
    # passes -- proves the payload-decode failure path is reached
    # independently of the signature-decode failure path above.
    import hmac as hmac_module
    import hashlib

    from src.api.auth.jwt_handler import _b64url_encode, _HEADER
    import json

    header_b64 = _b64url_encode(json.dumps(_HEADER, separators=(",", ":")).encode("utf-8"))
    payload_b64 = "not-valid-base64!!!"
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac_module.new(_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    forged = f"{header_b64}.{payload_b64}.{signature_b64}"

    with pytest.raises(JWTError, match="payload is not valid base64url-encoded JSON"):
        decode(forged, _SECRET)


def test_decode_rejects_unsupported_algorithm():
    # Manually crafted token with alg=none, a classic JWT vulnerability class --
    # decode() must never accept it.
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "admin"}).encode()).rstrip(b"=").decode()
    forged = f"{header}.{payload}."
    with pytest.raises(JWTError, match="unsupported or missing algorithm"):
        decode(forged, _SECRET)


def test_expired_token_is_rejected():
    now = time.time()
    token = encode({"sub": "admin", "exp": now - 10}, _SECRET)
    with pytest.raises(JWTError, match="expired"):
        decode(token, _SECRET)


def test_token_without_exp_claim_never_expires():
    token = encode({"sub": "admin"}, _SECRET)
    claims = decode(token, _SECRET)
    assert claims["sub"] == "admin"


def test_create_access_token_has_correct_type_and_expiry():
    token = create_access_token("admin", _SECRET, expires_in_seconds=900)
    claims = decode(token, _SECRET)
    assert claims["token_type"] == "access"
    assert claims["sub"] == "admin"
    assert claims["exp"] > claims["iat"]


def test_create_refresh_token_has_correct_type():
    token = create_refresh_token("admin", _SECRET, expires_in_seconds=604800)
    claims = decode(token, _SECRET)
    assert claims["token_type"] == "refresh"


def test_decode_token_of_type_rejects_refresh_presented_as_access():
    refresh_token = create_refresh_token("admin", _SECRET, expires_in_seconds=604800)
    with pytest.raises(JWTError, match="expected a 'access' token"):
        decode_token_of_type(refresh_token, _SECRET, expected_type="access")


def test_decode_token_of_type_rejects_access_presented_as_refresh():
    access_token = create_access_token("admin", _SECRET, expires_in_seconds=900)
    with pytest.raises(JWTError, match="expected a 'refresh' token"):
        decode_token_of_type(access_token, _SECRET, expected_type="refresh")


def test_subject_from_access_token_returns_subject_for_valid_token():
    token = create_access_token("admin", _SECRET, expires_in_seconds=900)
    assert subject_from_access_token(token, _SECRET) == "admin"


def test_subject_from_access_token_returns_none_for_invalid_token():
    assert subject_from_access_token("garbage", _SECRET) is None


def test_subject_from_access_token_returns_none_for_expired_token():
    now = time.time()
    token = encode({"sub": "admin", "token_type": "access", "exp": now - 1}, _SECRET)
    assert subject_from_access_token(token, _SECRET) is None


def test_subject_from_access_token_returns_none_for_refresh_token():
    refresh_token = create_refresh_token("admin", _SECRET, expires_in_seconds=604800)
    assert subject_from_access_token(refresh_token, _SECRET) is None
