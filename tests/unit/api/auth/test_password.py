"""Unit tests for src.api.auth.password (PBKDF2-HMAC-SHA256, single
fixed application-wide salt -- see module docstring for scope)."""

from src.api.auth.password import hash_password, verify_password

_SECRET = "test-secret-key"


def test_correct_password_verifies():
    hashed = hash_password("correct horse battery staple", _SECRET)
    assert verify_password("correct horse battery staple", hashed, _SECRET) is True


def test_incorrect_password_does_not_verify():
    hashed = hash_password("correct horse battery staple", _SECRET)
    assert verify_password("wrong password", hashed, _SECRET) is False


def test_hash_is_not_the_plaintext_password():
    hashed = hash_password("correct horse battery staple", _SECRET)
    assert "correct horse battery staple" not in hashed


def test_hash_is_deterministic_for_the_same_secret_key():
    a = hash_password("correct horse battery staple", _SECRET)
    b = hash_password("correct horse battery staple", _SECRET)
    assert a == b


def test_hash_differs_across_different_secret_keys():
    a = hash_password("correct horse battery staple", "secret-a")
    b = hash_password("correct horse battery staple", "secret-b")
    assert a != b


def test_verify_password_rejects_empty_stored_hash():
    assert verify_password("anything", "", _SECRET) is False


def test_verify_password_rejects_malformed_stored_hash():
    assert verify_password("anything", "not-valid-hex-!!", _SECRET) is False
