"""Unit tests for src.core.monitoring.secret_masking -- the one place a
sensitive value is turned into a safe-to-log representation."""

from src.core.monitoring.secret_masking import (
    is_sensitive_field_name,
    mask_dict_values,
    mask_secret,
)


def test_is_sensitive_field_name_matches_common_secret_names():
    for name in (
        "secret_key", "SECRET_KEY", "password", "api_key", "OPENAI_API_KEY",
        "access_token", "refresh_token", "private_key", "credential",
        "authorization", "sentry_dsn", "database_connection_string",
    ):
        assert is_sensitive_field_name(name), name


def test_is_sensitive_field_name_leaves_ordinary_names_alone():
    for name in ("request_id", "user_id", "symbol", "status", "duration_seconds"):
        assert not is_sensitive_field_name(name), name


def test_mask_secret_keeps_prefix_and_suffix_for_long_values():
    assert mask_secret("sk-abcdefghijklmnopqrstuvwxyz") == "sk-a...wxyz"


def test_mask_secret_fully_masks_short_values():
    assert mask_secret("short") == "***"


def test_mask_secret_handles_none():
    assert mask_secret(None) == "None"


def test_mask_dict_values_only_masks_sensitive_keys():
    original = {"symbol": "2222", "api_key": "sk-abcdefghijklmnopqrstuvwxyz"}
    masked = mask_dict_values(original)

    assert masked["symbol"] == "2222"
    assert masked["api_key"] == "sk-a...wxyz"
    # never mutates the caller's dict
    assert original["api_key"] == "sk-abcdefghijklmnopqrstuvwxyz"


def test_mask_dict_values_recurses_into_nested_dicts():
    original = {
        "request": {
            "headers": {"authorization": "Bearer sk-abcdefghijklmnopqrstuvwxyz"},
            "path": "/api/v1/auth/login",
        }
    }
    masked = mask_dict_values(original)

    assert masked["request"]["headers"]["authorization"] == "Bear...wxyz"
    assert masked["request"]["path"] == "/api/v1/auth/login"
    # never mutates the caller's (nested) dict either
    assert original["request"]["headers"]["authorization"] == "Bearer sk-abcdefghijklmnopqrstuvwxyz"


def test_mask_dict_values_recurses_into_lists_of_dicts():
    original = {"users": [{"email": "a@example.com", "password": "hunter2"}, {"email": "b@example.com"}]}
    masked = mask_dict_values(original)

    assert masked["users"][0]["email"] == "a@example.com"
    assert masked["users"][0]["password"] == "***"
    assert masked["users"][1]["email"] == "b@example.com"


def test_mask_dict_values_masks_a_sensitive_key_even_when_its_value_is_a_nested_structure():
    original = {"credentials": {"user": "admin", "pass": "hunter2"}}
    masked = mask_dict_values(original)

    # the whole nested structure is masked as one opaque value, since
    # the key itself ("credentials") is what marked it sensitive
    assert "admin" not in str(masked["credentials"])
    assert "hunter2" not in str(masked["credentials"])
