"""Unit tests for scripts/verify_sahmk_endpoint_coverage.py's exception
-> outcome classification (`_call`). Local only, no network -- exercises
the classifier against real exception classes raised by a fake
coroutine, not against a live SAHMK response. The one real, unmocked
verification lives in the script itself, run only by
.github/workflows/sahmk-live-verification.yml on manual dispatch.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from scripts.verify_sahmk_endpoint_coverage import _call  # noqa: E402
from src.market_data.sahmk.exceptions import (  # noqa: E402
    SahmkAuthenticationError,
    SahmkEntitlementError,
    SahmkRateLimitError,
    SahmkRequestError,
)


async def _raise(exc):
    raise exc


async def _return(value):
    return value


class TestCallClassification:
    @pytest.mark.asyncio
    async def test_successful_dict_response_is_ok(self):
        result = await _call("quote", "get_quote", _return({"symbol": "2222", "price": 1.0}))
        assert result.outcome == "OK"
        assert result.status_code == 200
        assert result.top_level_fields == ["price", "symbol"]

    @pytest.mark.asyncio
    async def test_auth_error_is_classified(self):
        result = await _call(
            "quote", "get_quote", _raise(SahmkAuthenticationError("bad key", status_code=401))
        )
        assert result.outcome == "AUTH_ERROR"
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_entitlement_error_is_classified(self):
        result = await _call(
            "financials", "get_financials", _raise(SahmkEntitlementError("plan limit", status_code=403))
        )
        assert result.outcome == "ENTITLEMENT_ERROR"
        assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_rate_limit_error_is_classified(self):
        result = await _call(
            "quote", "get_quote", _raise(SahmkRateLimitError("too many requests"))
        )
        assert result.outcome == "RATE_LIMITED"

    @pytest.mark.asyncio
    async def test_generic_request_error_is_classified(self):
        result = await _call(
            "companies", "get_companies", _raise(SahmkRequestError("boom", status_code=500))
        )
        assert result.outcome == "REQUEST_ERROR"
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_unexpected_exception_never_crashes_the_sweep(self):
        result = await _call("dividends", "get_dividends", _raise(ValueError("weird")))
        assert result.outcome == "UNEXPECTED_ERROR"
        assert "ValueError" in result.detail

    @pytest.mark.asyncio
    async def test_non_dict_response_has_no_top_level_fields(self):
        result = await _call("companies", "get_companies", _return([1, 2, 3]))
        assert result.outcome == "OK"
        assert result.top_level_fields == []
