"""Unit tests for src.api.auth.api_key."""

from src.api.auth.api_key import verify_api_key


def test_matching_keys_verify():
    assert verify_api_key("secret-key-123", "secret-key-123") is True


def test_mismatched_keys_do_not_verify():
    assert verify_api_key("wrong-key", "secret-key-123") is False


def test_none_presented_key_never_verifies():
    assert verify_api_key(None, "secret-key-123") is False


def test_empty_presented_key_never_verifies():
    assert verify_api_key("", "secret-key-123") is False


def test_unconfigured_key_never_verifies_even_against_empty_presented_key():
    assert verify_api_key("", None) is False
    assert verify_api_key("anything", None) is False
    assert verify_api_key("anything", "") is False
