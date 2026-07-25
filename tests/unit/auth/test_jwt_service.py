import time

import jwt as pyjwt
import pytest

from src.auth.jwt_service import InvalidAccessTokenError, decode_access_token, encode_access_token
from src.core.config import settings


def test_encode_then_decode_round_trip():
    token = encode_access_token(user_id=42, is_staff=False, staff_role=None)
    claims = decode_access_token(token)
    assert claims["sub"] == "42"
    assert claims["is_staff"] is False
    assert claims["staff_role"] is None
    assert claims["type"] == "access"


def test_staff_claims_carried_through():
    token = encode_access_token(user_id=7, is_staff=True, staff_role="ADMIN")
    claims = decode_access_token(token)
    assert claims["is_staff"] is True
    assert claims["staff_role"] == "ADMIN"


def test_garbage_token_rejected():
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not.a.valid.jwt")


def test_wrong_signature_rejected():
    token = encode_access_token(user_id=1, is_staff=False, staff_role=None)
    tampered = token[:-4] + "abcd"
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(tampered)


def test_expired_token_rejected():
    # Encode a token that's already expired by constructing it directly
    # (bypassing encode_access_token's fixed TTL) rather than sleeping.
    claims = {
        "sub": "1",
        "is_staff": False,
        "staff_role": None,
        "jti": "x",
        "iat": int(time.time()) - 3600,
        "exp": int(time.time()) - 1800,
        "type": "access",
    }
    token = pyjwt.encode(claims, settings.secret_key, algorithm="HS256")
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_non_access_token_type_rejected():
    claims = {
        "sub": "1",
        "is_staff": False,
        "staff_role": None,
        "jti": "x",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "type": "refresh",
    }
    token = pyjwt.encode(claims, settings.secret_key, algorithm="HS256")
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)
