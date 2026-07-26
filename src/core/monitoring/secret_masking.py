"""Shared secret-masking helpers -- the one place a sensitive value is
turned into a safe-to-log/safe-to-display representation, used by
`structured_logging.py` (automatic masking of suspiciously-named log
fields) and by anything that needs to show a human "yes, a key is
configured" without ever showing the key itself (e.g. an admin
diagnostics endpoint).
"""

import re
from typing import Any

# Case-insensitive substrings that mark a field/key name as sensitive.
# Deliberately broad (better to over-mask an innocuous field than to
# under-mask a real secret) -- "id" is excluded on its own since
# "request_id"/"user_id" are common, harmless, and would otherwise
# collide with "credential".
_SENSITIVE_NAME_PATTERN = re.compile(
    r"(secret|password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"private[_-]?key|credential|authorization|dsn|connection[_-]?string)",
    re.IGNORECASE,
)


def is_sensitive_field_name(name: str) -> bool:
    return bool(_SENSITIVE_NAME_PATTERN.search(name))


def mask_secret(value: Any, keep: int = 4) -> str:
    """Reduce a secret to a form that proves *a* value is configured
    without revealing it: `"sk-abcd...wxyz"` for anything long enough
    to have a meaningful prefix/suffix, `"***"` for short values (a
    partial masking of a 4-character secret would leak most of it)."""
    if value is None:
        return "None"
    text = str(value)
    if len(text) <= keep * 2:
        return "***"
    return f"{text[:keep]}...{text[-keep:]}"


def mask_dict_values(data: dict) -> dict:
    """Return a shallow copy of `data` with every value whose key name
    looks sensitive replaced by `mask_secret()`. Never mutates the
    input -- callers (e.g. the JSON log formatter) must not have a log
    call's caller-visible `extra_fields` dict altered out from under
    them."""
    return {
        key: (mask_secret(value) if is_sensitive_field_name(str(key)) else value)
        for key, value in data.items()
    }
