"""Password hashing via the `bcrypt` package directly (not passlib --
see requirements.txt's `# Auth & Security` section for why: passlib
1.7.4 is unmaintained and breaks under current bcrypt releases).

bcrypt has a hard 72-byte input limit (silently ignores anything past
byte 72 in older APIs, raises in this version) -- rather than truncate
a password (which would silently weaken it and is surprising), a
too-long password is rejected here with a clear error. In practice
Pydantic schemas at the API layer (src/api/schemas/auth.py) already
cap password length well under 72 bytes, so this is a defensive floor,
not the primary validation.
"""

import bcrypt

_MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    pass


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(f"Password exceeds bcrypt's {_MAX_PASSWORD_BYTES}-byte limit.")
    hashed = bcrypt.hashpw(encoded, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/unrecognized hash -- treat as "does not verify",
        # never raise past this boundary (a corrupt stored hash must
        # not become a 500 on every login attempt for that account).
        return False
