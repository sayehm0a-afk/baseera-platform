"""Unit tests for src.api.schemas.auth's request validation -- pure
Pydantic-level checks, no DB/network needed.

2026-09 audit finding: RegisterRequest/ResetPasswordRequest only
enforced a minimum length (8 chars) on a new password, letting a
purely-repeated or purely-numeric string like "aaaaaaaa"/"12345678"
through. These tests are the regression coverage for the fix -- a
letter-and-digit requirement applied only to NEW passwords
(registration, reset), never to LoginRequest, so no existing account's
ability to log in is affected."""

import pytest
from pydantic import ValidationError

from src.api.schemas.auth import LoginRequest, RegisterRequest, ResetPasswordRequest


class TestRegisterRequestPasswordComplexity:
    def test_accepts_a_letter_and_digit_password(self):
        req = RegisterRequest(email="user@example.com", password="s3cret-password")
        assert req.password == "s3cret-password"

    def test_rejects_all_letters(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="aaaaaaaa")

    def test_rejects_all_digits(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="12345678")

    def test_rejects_letters_and_symbols_but_no_digit(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="another-pass")

    def test_arabic_letters_count_as_letters(self):
        """Non-Latin scripts must not be treated as "not a letter" --
        a Saudi user typing an Arabic password is a real, expected case."""
        req = RegisterRequest(email="user@example.com", password="كلمةسر1234")
        assert req.password == "كلمةسر1234"

    def test_still_enforces_the_pre_existing_minimum_length(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="a1")


class TestResetPasswordRequestPasswordComplexity:
    def test_accepts_a_letter_and_digit_password(self):
        req = ResetPasswordRequest(token="tok", new_password="brand-new-password1")
        assert req.new_password == "brand-new-password1"

    def test_rejects_a_password_with_no_digit(self):
        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="tok", new_password="brand-new-password")


def test_login_request_never_validates_password_complexity():
    """An EXISTING account's password (created before this rule existed,
    or intentionally simple) must always still be able to log in --
    complexity is a new-password rule only."""
    req = LoginRequest(email="user@example.com", password="aaaaaaaa")
    assert req.password == "aaaaaaaa"
