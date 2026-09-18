"""Unit tests for PolygonError.sanitized_provider_detail() -- mirrors
tests/unit/market_data/sahmk/test_exceptions.py exactly, proving the
same three required properties for the Polygon exception hierarchy:
the real body is recoverable, `str(exc)` itself is unchanged, and no
credential-shaped content can ever leak into a persisted log line."""

import json

from src.market_data.polygon.exceptions import (
    PolygonAuthenticationError,
    PolygonError,
    PolygonRateLimitError,
    PolygonRequestError,
)


def test_sanitized_provider_detail_returns_the_real_dict_body_as_json():
    exc = PolygonAuthenticationError(
        "Polygon rejected the configured API key (401).",
        status_code=401,
        body={"status": "ERROR", "message": "Unknown API Key"},
    )
    detail = exc.sanitized_provider_detail()
    assert json.loads(detail) == {"status": "ERROR", "message": "Unknown API Key"}


def test_sanitized_provider_detail_returns_raw_text_body_unchanged():
    exc = PolygonRequestError(
        "Polygon request failed with status 429.", status_code=429, body="Too Many Requests"
    )
    assert exc.sanitized_provider_detail() == "Too Many Requests"


def test_sanitized_provider_detail_is_empty_string_when_no_body_was_captured():
    exc = PolygonRequestError("Network error calling Polygon API: timeout", status_code=None, body=None)
    assert exc.sanitized_provider_detail() == ""


def test_str_of_exception_is_unchanged_by_this_fix():
    exc = PolygonAuthenticationError(
        "Polygon rejected the configured API key (401).", status_code=401, body={"message": "Unknown API Key"}
    )
    assert str(exc) == "Polygon rejected the configured API key (401)."


def test_body_attribute_still_directly_accessible():
    exc = PolygonAuthenticationError("x", status_code=401, body={"error": "invalid key"})
    assert exc.body == {"error": "invalid key"}


# --- redaction: no credential-shaped content may ever survive --------------


def test_redacts_x_api_key_field_and_produces_valid_json():
    exc = PolygonRequestError(
        "x", status_code=500, body={"X-API-Key": "realkeyvalue123", "message": "unrelated"}
    )
    detail = exc.sanitized_provider_detail()
    assert "realkeyvalue123" not in detail
    parsed = json.loads(detail)
    assert parsed["X-API-Key"] == "[REDACTED]"
    assert parsed["message"] == "unrelated"


def test_redacts_authorization_bearer_token():
    exc = PolygonRequestError(
        "x", status_code=500, body={"detail": "Authorization: Bearer sk_live_abc123XYZ leaked"}
    )
    detail = exc.sanitized_provider_detail()
    assert "sk_live_abc123XYZ" not in detail


def test_redacts_secret_and_token_fields():
    exc = PolygonRequestError(
        "x", status_code=500, body={"secret": "shh_dont_tell", "token": "tok_9f8e7d", "ok": True}
    )
    detail = exc.sanitized_provider_detail()
    assert "shh_dont_tell" not in detail
    assert "tok_9f8e7d" not in detail
    parsed = json.loads(detail)
    assert parsed["ok"] is True


def test_redacts_cookie_field():
    exc = PolygonRequestError("x", status_code=500, body={"cookie": "session_id_do_not_leak"})
    detail = exc.sanitized_provider_detail()
    assert "session_id_do_not_leak" not in detail


def test_ordinary_field_named_message_or_status_is_never_redacted():
    exc = PolygonAuthenticationError(
        "x", status_code=401, body={"status": "ERROR", "message": "Unknown API Key"}
    )
    detail = exc.sanitized_provider_detail()
    parsed = json.loads(detail)
    assert parsed == {"status": "ERROR", "message": "Unknown API Key"}


# --- size bound --------------------------------------------------------


def test_oversized_body_is_truncated_with_a_bounded_length():
    exc = PolygonRequestError("x", status_code=500, body={"detail": "A" * 10_000})
    detail = exc.sanitized_provider_detail()
    assert len(detail) <= 2050
    assert detail.endswith("...<truncated>")


# --- malformed / non-JSON-serializable bodies never break ingestion --------


def test_non_json_serializable_body_falls_back_to_str_without_raising():
    class Weird:
        def __str__(self):
            return "weird-object-repr"

    exc = PolygonRequestError("x", status_code=500, body=Weird())
    detail = exc.sanitized_provider_detail()
    assert detail == "weird-object-repr"


def test_list_body_is_serialized_as_json():
    exc = PolygonRequestError("x", status_code=500, body=[{"field": "value"}])
    detail = exc.sanitized_provider_detail()
    assert json.loads(detail) == [{"field": "value"}]


# --- applies uniformly across the exception hierarchy -----------------


def test_every_polygon_error_subclass_supports_sanitized_provider_detail():
    for cls, kwargs in [
        (PolygonAuthenticationError, {}),
        (PolygonRequestError, {}),
        (PolygonRateLimitError, {"retry_after": 60}),
    ]:
        exc = cls("msg", status_code=403, body={"k": "v"}, **kwargs)
        assert isinstance(exc, PolygonError)
        assert exc.sanitized_provider_detail() == '{"k": "v"}'


def test_rate_limit_error_carries_retry_after():
    exc = PolygonRateLimitError("rate limited", retry_after=12.5)
    assert exc.retry_after == 12.5
