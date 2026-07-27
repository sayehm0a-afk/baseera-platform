import pytest

from src.auth.password_hashing import PasswordTooLongError, hash_password, verify_password


def test_hash_then_verify_round_trip():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True


def test_wrong_password_does_not_verify():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", hashed) is False


def test_hash_is_never_the_plaintext():
    hashed = hash_password("my-secret-password")
    assert hashed != "my-secret-password"
    assert hashed.startswith("$2b$")


def test_password_over_72_bytes_rejected_on_hash():
    with pytest.raises(PasswordTooLongError):
        hash_password("x" * 73)


def test_password_over_72_bytes_fails_verify_gracefully_not_raise():
    hashed = hash_password("a-normal-password")
    assert verify_password("x" * 73, hashed) is False


def test_malformed_hash_fails_verify_gracefully_not_raise():
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False
