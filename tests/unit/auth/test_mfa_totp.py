"""Unit tests for src.auth.mfa_totp -- the crypto/TOTP primitives behind
optional staff 2FA (governance audit 2026-09-11, item 7)."""

import datetime

import pyotp
import pytest

from src.auth import mfa_totp
from src.core.config import settings


def test_generate_totp_secret_is_a_valid_base32_string():
    secret = mfa_totp.generate_totp_secret()
    # A valid base32 secret must be decodable and non-trivially long --
    # pyotp itself would raise on a malformed one when constructing TOTP.
    pyotp.TOTP(secret)
    assert len(secret) >= 16


def test_generate_totp_secret_is_unique_per_call():
    secrets_generated = {mfa_totp.generate_totp_secret() for _ in range(20)}
    assert len(secrets_generated) == 20


def test_encrypt_decrypt_roundtrip():
    secret = mfa_totp.generate_totp_secret()
    encrypted = mfa_totp.encrypt_secret(secret)
    assert encrypted != secret  # never stored in plaintext
    assert mfa_totp.decrypt_secret(encrypted) == secret


def test_encrypted_secret_is_not_decryptable_with_a_different_signing_key(monkeypatch):
    secret = mfa_totp.generate_totp_secret()
    encrypted = mfa_totp.encrypt_secret(secret)

    monkeypatch.setattr(settings, "secret_key", "a-completely-different-secret-key-value")

    with pytest.raises(mfa_totp.InvalidTotpCodeError):
        mfa_totp.decrypt_secret(encrypted)


def test_decrypt_corrupted_value_raises_invalid_totp_code_error():
    with pytest.raises(mfa_totp.InvalidTotpCodeError):
        mfa_totp.decrypt_secret("not-a-real-fernet-token")


def test_provisioning_uri_contains_issuer_and_account_email():
    secret = mfa_totp.generate_totp_secret()
    uri = mfa_totp.provisioning_uri(secret, "owner@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "Basirah" in uri
    assert "owner%40example.com" in uri or "owner@example.com" in uri


def test_verify_totp_code_accepts_the_current_real_code():
    secret = mfa_totp.generate_totp_secret()
    current_code = pyotp.TOTP(secret).now()
    assert mfa_totp.verify_totp_code(secret, current_code) is True


def test_verify_totp_code_rejects_a_wrong_code():
    secret = mfa_totp.generate_totp_secret()
    assert mfa_totp.verify_totp_code(secret, "000000") is False


def test_verify_totp_code_rejects_a_code_from_a_different_secret():
    secret_a = mfa_totp.generate_totp_secret()
    secret_b = mfa_totp.generate_totp_secret()
    code_for_b = pyotp.TOTP(secret_b).now()
    assert mfa_totp.verify_totp_code(secret_a, code_for_b) is False


def test_verify_totp_code_never_raises_on_malformed_input():
    secret = mfa_totp.generate_totp_secret()
    assert mfa_totp.verify_totp_code(secret, "not-a-digit-code") is False
    assert mfa_totp.verify_totp_code(secret, "") is False


def test_get_matching_totp_step_returns_the_current_step_for_the_current_code():
    secret = mfa_totp.generate_totp_secret()
    totp = pyotp.TOTP(secret)
    current_code = totp.now()
    step = mfa_totp.get_matching_totp_step(secret, current_code)
    assert step == totp.timecode(datetime.datetime.now())


def test_get_matching_totp_step_returns_none_for_a_wrong_code():
    secret = mfa_totp.generate_totp_secret()
    assert mfa_totp.get_matching_totp_step(secret, "000000") is None


def test_get_matching_totp_step_distinguishes_adjacent_steps():
    secret = mfa_totp.generate_totp_secret()
    totp = pyotp.TOTP(secret)
    now = datetime.datetime.now()
    current_step = totp.timecode(now)

    assert mfa_totp.get_matching_totp_step(secret, totp.at(now, -1)) == current_step - 1
    assert mfa_totp.get_matching_totp_step(secret, totp.at(now, 0)) == current_step
    assert mfa_totp.get_matching_totp_step(secret, totp.at(now, 1)) == current_step + 1


def test_get_matching_totp_step_rejects_a_code_outside_the_valid_window():
    secret = mfa_totp.generate_totp_secret()
    totp = pyotp.TOTP(secret)
    now = datetime.datetime.now()
    assert mfa_totp.get_matching_totp_step(secret, totp.at(now, 2)) is None


def test_generate_backup_codes_returns_the_requested_count_all_unique():
    codes = mfa_totp.generate_backup_codes(count=10)
    assert len(codes) == 10
    assert len(set(codes)) == 10


def test_generate_backup_codes_default_count():
    assert len(mfa_totp.generate_backup_codes()) == 10
