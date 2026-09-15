"""Optional TOTP-based 2FA for OWNER/ADMIN staff accounts (governance
audit `docs/governance/تدقيق_شامل_للمنصة_2026-09-11.md`, item 7).

Opt-in only, by construction: nothing in this module runs unless a staff
member explicitly calls the enrollment routes (`src/api/routes/mfa.py`)
for their own account -- no existing account's login behavior changes
until it does. This is the deliberate safety property that makes shipping
this without per-account migration/backfill work safe: `User.mfa_enabled`
defaults to `False` for every row, old and new alike.

The TOTP secret must be stored in a form the server can read back (unlike
a password, verifying a code requires recomputing HMAC-based codes from
the raw secret) -- so it is encrypted at rest with Fernet (AES-128-CBC +
HMAC, authenticated) rather than left in plaintext, using a key derived
from `settings.secret_key` via HKDF rather than a second secret the
deployment would have to manage. This is a confidentiality-at-rest
measure only (a DB leak alone doesn't hand out live codes) -- it is not a
substitute for `settings.secret_key` itself being kept secret, since
whoever holds that can already derive this same key.

Backup codes reuse `src.auth.token_hashing`'s exact "generate high-entropy
value, persist only its hash" discipline already applied to password-
reset/email-verification/refresh tokens -- a leaked `MfaBackupCode` row
hands out nothing usable.
"""

import base64
import secrets
from typing import List

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.core.config import settings

_ISSUER_NAME = "Basirah"
_HKDF_INFO = b"baseerah-mfa-totp-secret-encryption-v1"

# TOTP defaults (RFC 6238): 30-second step, 6 digits, SHA1 -- the same
# parameters every authenticator app (Google Authenticator, Authy, 1Password)
# assumes when scanning a plain otpauth:// URI with none specified.
_VALID_WINDOW = 1  # accepts the previous/next 30s step too, for clock drift

_BACKUP_CODE_COUNT = 10
_BACKUP_CODE_BYTES = 5  # 10 hex chars -> e.g. "3f9a1c7b02"


class InvalidTotpCodeError(Exception):
    pass


def _fernet() -> Fernet:
    """Derives a Fernet key from `settings.secret_key` -- never a second
    standalone secret to provision/rotate/leak independently. Recomputed
    per call (cheap) rather than cached at import time so a test can
    freely monkeypatch `settings.secret_key` and see it take effect."""
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO)
    key = kdf.derive(settings.secret_key.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def generate_totp_secret() -> str:
    """A fresh base32 secret, per `pyotp`'s own RFC-4648-compliant
    generator -- never reused across users or across a re-enrollment."""
    return pyotp.random_base32()


def encrypt_secret(raw_secret: str) -> str:
    return _fernet().encrypt(raw_secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_secret: str) -> str:
    """Raises `InvalidTotpCodeError` (not a bare cryptography exception)
    on a corrupted/foreign-key-encrypted value -- callers already treat
    that exception as "this code cannot be correct," which is the right
    outcome here too: a secret that fails to decrypt can never produce a
    matching code."""
    try:
        return _fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise InvalidTotpCodeError("Stored MFA secret could not be decrypted.") from exc


def provisioning_uri(raw_secret: str, account_email: str) -> str:
    """`otpauth://` URI for a QR code -- every authenticator app scans
    this directly; `account_email` and `_ISSUER_NAME` are display-only
    (shown in the app's account list), never used in verification."""
    return pyotp.TOTP(raw_secret).provisioning_uri(name=account_email, issuer_name=_ISSUER_NAME)


def verify_totp_code(raw_secret: str, code: str) -> bool:
    """`code` is untrusted user input -- pyotp's own `verify()` already
    handles a non-digit/wrong-length string as simply "not valid" rather
    than raising, so no extra validation is needed here."""
    return pyotp.TOTP(raw_secret).verify(code, valid_window=_VALID_WINDOW)


def generate_backup_codes(count: int = _BACKUP_CODE_COUNT) -> List[str]:
    """Raw, one-time-display codes -- the caller must hash each one
    (`src.auth.token_hashing.hash_token`) before persisting and must
    never log or store the raw values anywhere."""
    return [secrets.token_hex(_BACKUP_CODE_BYTES) for _ in range(count)]
