"""Unit tests for SahmkError.sanitized_provider_detail() -- the P0 raw-
provider-evidence observability fix.

A real 2026-08-31 Historical OHLCV production incident (49/49 symbols
failing with a generic "SAHMK plan does not permit this endpoint (403
PLAN_LIMIT)" message) could not be root-caused from persisted evidence:
`SahmkError.body` always captured the real upstream response, but every
caller that persisted a failure used `str(exc)`, which never included
it (`SahmkError.__init__` calls `super().__init__(message)` with only
the fixed message). These tests prove the fix's three required
properties: the real body is now recoverable, `str(exc)` itself is
unchanged (existing callers/tests keep their stable shape), and no
credential-shaped content can ever leak into a persisted log line.
"""

import json

from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkDailyQuotaExhaustedError,
    SahmkEntitlementError,
    SahmkError,
    SahmkRequestError,
)


def test_sanitized_provider_detail_returns_the_real_dict_body_as_json():
    exc = SahmkEntitlementError(
        "SAHMK plan does not permit this endpoint (403 PLAN_LIMIT).",
        status_code=403,
        body={"code": "HISTORICAL_PLAN_LIMIT", "message": "Historical data quota exceeded"},
    )
    detail = exc.sanitized_provider_detail()
    assert json.loads(detail) == {"code": "HISTORICAL_PLAN_LIMIT", "message": "Historical data quota exceeded"}


def test_sanitized_provider_detail_returns_raw_text_body_unchanged():
    exc = SahmkRequestError(
        "SAHMK request failed with status 429.",
        status_code=429,
        body="IP daily rate limit exceeded (100 requests/day)",
    )
    assert exc.sanitized_provider_detail() == "IP daily rate limit exceeded (100 requests/day)"


def test_sanitized_provider_detail_is_empty_string_when_no_body_was_captured():
    exc = SahmkRequestError("Network error calling SAHMK API: timeout", status_code=None, body=None)
    assert exc.sanitized_provider_detail() == ""


def test_str_of_exception_is_unchanged_by_this_fix():
    """The existing, stable str(exc) shape (relied on by other tests
    and by SahmkClient's own docstrings/tests) must never include the
    body -- sanitized_provider_detail() is additive, called explicitly
    by whoever wants the real evidence, never folded into __str__."""
    exc = SahmkEntitlementError(
        "SAHMK plan does not permit this endpoint (403 PLAN_LIMIT).",
        status_code=403,
        body={"code": "HISTORICAL_PLAN_LIMIT"},
    )
    assert str(exc) == "SAHMK plan does not permit this endpoint (403 PLAN_LIMIT)."


def test_body_attribute_still_directly_accessible():
    """Pre-existing contract (test_client.py's own
    test_403_raises_entitlement_error_with_body) must keep working."""
    exc = SahmkEntitlementError("x", status_code=403, body={"error": "PLAN_LIMIT"})
    assert exc.body == {"error": "PLAN_LIMIT"}


# --- redaction: no credential-shaped content may ever survive --------------


def test_redacts_x_api_key_field_and_produces_valid_json():
    exc = SahmkRequestError(
        "x", status_code=500, body={"X-API-Key": "realkeyvalue123", "message": "unrelated"}
    )
    detail = exc.sanitized_provider_detail()
    assert "realkeyvalue123" not in detail
    parsed = json.loads(detail)
    assert parsed["X-API-Key"] == "[REDACTED]"
    assert parsed["message"] == "unrelated"


def test_redacts_authorization_bearer_token():
    exc = SahmkRequestError("x", status_code=500, body={"detail": "Authorization: Bearer sk_live_abc123XYZ leaked"})
    detail = exc.sanitized_provider_detail()
    assert "sk_live_abc123XYZ" not in detail


def test_redacts_secret_and_token_fields():
    exc = SahmkRequestError("x", status_code=500, body={"secret": "shh_dont_tell", "token": "tok_9f8e7d", "ok": True})
    detail = exc.sanitized_provider_detail()
    assert "shh_dont_tell" not in detail
    assert "tok_9f8e7d" not in detail
    parsed = json.loads(detail)
    assert parsed["ok"] is True


def test_redacts_cookie_field():
    exc = SahmkRequestError("x", status_code=500, body={"cookie": "session_id_do_not_leak"})
    detail = exc.sanitized_provider_detail()
    assert "session_id_do_not_leak" not in detail


def test_ordinary_field_named_message_or_code_is_never_redacted():
    """Sanity check that redaction is scoped to credential-shaped keys
    only -- a normal SAHMK error payload must survive intact."""
    exc = SahmkEntitlementError(
        "x", status_code=403, body={"code": "HISTORICAL_PLAN_LIMIT", "message": "Historical data quota exceeded"}
    )
    detail = exc.sanitized_provider_detail()
    parsed = json.loads(detail)
    assert parsed == {"code": "HISTORICAL_PLAN_LIMIT", "message": "Historical data quota exceeded"}


# --- size bound --------------------------------------------------------


def test_oversized_body_is_truncated_with_a_bounded_length():
    exc = SahmkRequestError("x", status_code=500, body={"detail": "A" * 10_000})
    detail = exc.sanitized_provider_detail()
    assert len(detail) <= 2050  # generous slack over the 2000-char cap for the "...<truncated>" suffix
    assert detail.endswith("...<truncated>")


# --- malformed / non-JSON-serializable bodies never break ingestion --------


def test_non_json_serializable_body_falls_back_to_str_without_raising():
    class Weird:
        def __str__(self):
            return "weird-object-repr"

    exc = SahmkRequestError("x", status_code=500, body=Weird())
    detail = exc.sanitized_provider_detail()
    assert detail == "weird-object-repr"


def test_list_body_is_serialized_as_json():
    exc = SahmkRequestError("x", status_code=500, body=[{"field": "value"}])
    detail = exc.sanitized_provider_detail()
    assert json.loads(detail) == [{"field": "value"}]


# --- applies uniformly across the exception hierarchy -----------------


def test_every_sahmk_error_subclass_supports_sanitized_provider_detail():
    for cls, kwargs in [
        (SahmkAuthenticationError, {}),
        (SahmkEntitlementError, {}),
        (SahmkRequestError, {}),
        (SahmkDailyQuotaExhaustedError, {"retry_after_seconds": 60}),
    ]:
        exc = cls("msg", status_code=403, body={"k": "v"}, **kwargs)
        assert isinstance(exc, SahmkError)
        assert exc.sanitized_provider_detail() == '{"k": "v"}'
