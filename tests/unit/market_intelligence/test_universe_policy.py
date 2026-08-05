"""Tests for src.market_intelligence.universe_policy.

Every case here is grounded in the exact real fields SAHMK's live
/companies/ directory has been confirmed to return (symbol, name_ar,
name_en, is_etf, market, market_segment, security_type, status --
see service.py's get_company_directory docstring and the 2026-08-02
live workflow runs). No case invents a field name that hasn't
actually been observed on the wire.
"""

from src.market_data.sahmk.models import SahmkCompanyProfile
from src.market_intelligence.universe_policy import classify_universe


def _profile(symbol: str, **raw_overrides) -> SahmkCompanyProfile:
    raw = {
        "symbol": symbol,
        "name_ar": f"{symbol}-ar",
        "name_en": f"{symbol}-en",
        "is_etf": False,
        "market": "Tadawul",
        "market_segment": "Main Market",
        "security_type": "Common Share",
        "status": "Active",
    }
    raw.update(raw_overrides)
    return SahmkCompanyProfile(
        symbol=symbol,
        name=raw.get("name_en"),
        name_ar=None,
        sector=None,
        industry=None,
        exchange=None,
        raw=raw,
    )


class TestEligibleCommonEquity:
    def test_main_market_common_equity_is_eligible(self):
        result = classify_universe([_profile("1010")])
        assert result.total_eligible == 1
        assert result.eligible_symbols == ["1010"]
        assert result.classifications[0].bucket == "MAIN_MARKET_EQUITY"
        assert result.classifications[0].exclusion_reason is None

    def test_missing_market_segment_defaults_to_main_market(self):
        result = classify_universe([_profile("1020", market_segment=None)])
        assert result.classifications[0].eligible is True
        assert result.classifications[0].bucket == "MAIN_MARKET_EQUITY"

    def test_nomu_common_equity_is_eligible_and_separately_bucketed(self):
        result = classify_universe([_profile("9300", market_segment="Nomu Parallel Market")])
        assert result.classifications[0].eligible is True
        assert result.classifications[0].bucket == "NOMU_EQUITY"


class TestExclusions:
    def test_etf_flag_excludes_regardless_of_security_type(self):
        result = classify_universe([_profile("ETF1", is_etf=True)])
        c = result.classifications[0]
        assert c.eligible is False
        assert c.bucket == "ETF_FUND"
        assert "is_etf" in c.exclusion_reason

    def test_reit_security_type_excluded(self):
        result = classify_universe([_profile("4330", security_type="REIT Fund")])
        c = result.classifications[0]
        assert c.eligible is False
        assert c.bucket == "REIT"

    def test_sukuk_security_type_excluded(self):
        result = classify_universe([_profile("SUK1", security_type="Sukuk")])
        assert result.classifications[0].bucket == "SUKUK_BOND"
        assert result.classifications[0].eligible is False

    def test_rights_issue_excluded(self):
        result = classify_universe([_profile("R001", security_type="Rights Issue")])
        assert result.classifications[0].bucket == "RIGHTS_ISSUE"

    def test_suspended_status_excluded(self):
        result = classify_universe([_profile("2210", status="Suspended")])
        c = result.classifications[0]
        assert c.eligible is False
        assert c.bucket == "SUSPENDED"

    def test_delisted_status_excluded(self):
        result = classify_universe([_profile("9999", status="Delisted")])
        assert result.classifications[0].bucket == "INACTIVE_DELISTED"

    def test_unrecognized_security_type_excluded_not_assumed_eligible(self):
        """A real /companies/ item with a security_type this policy has
        never seen must NOT be silently treated as eligible common
        equity -- it must land in a clearly-labeled bucket with the
        literal observed value in the reason, per the mandate's
        'do not hardcode / do not guess' requirement. It IS however
        deliberately still eligible -- see the module docstring on why
        this policy is deny-list, not allow-list: a security_type this
        code has never seen is not a positive signal of exclusion, and
        silently dropping it would risk zeroing out the whole universe
        on an unconfirmed string mismatch."""
        result = classify_universe([_profile("WEIRD", security_type="Preferred Stock XYZ")])
        c = result.classifications[0]
        assert c.eligible is True
        assert "TYPE_UNCONFIRMED" in c.bucket

    def test_unrecognized_status_not_excluded_but_flagged_unconfirmed(self):
        result = classify_universe([_profile("WEIRD2", status="Pending Review")])
        c = result.classifications[0]
        assert c.eligible is True
        assert "STATUS_UNCONFIRMED" in c.bucket

    def test_unrecognized_market_segment_not_excluded_but_flagged_unconfirmed(self):
        result = classify_universe([_profile("WEIRD3", market_segment="Some Other Board")])
        c = result.classifications[0]
        assert c.eligible is True
        assert c.bucket == "MAIN_MARKET_EQUITY_SEGMENT_UNCONFIRMED"


class TestDenyListSafetyNet:
    """Regression coverage for the exact risk found before this policy
    shipped: an allow-list design would have excluded a whole universe
    of otherwise-normal common equities the moment the real SAHMK
    security_type/status string didn't happen to contain one of a
    small set of guessed substrings."""

    def test_entirely_unrecognized_type_and_status_still_eligible(self):
        result = classify_universe(
            [_profile(s, security_type="Unknown-Value-ABC", status="Unknown-Value-123") for s in ["1", "2", "3"]]
        )
        assert result.total_eligible == 3
        assert result.total_excluded == 0

    def test_a_realistic_100_symbol_universe_of_unconfirmed_values_is_not_zeroed(self):
        companies = [
            _profile(str(1000 + i), security_type="Ordinary Shares SAR 10", status="ACTIVE_TRADING")
            for i in range(100)
        ]
        result = classify_universe(companies)
        assert result.total_eligible == 100
        assert result.total_excluded == 0


class TestAggregateAccounting:
    def test_bucket_counts_and_eligible_count_are_consistent(self):
        companies = [
            _profile("1010"),
            _profile("1020"),
            _profile("ETF1", is_etf=True),
            _profile("4330", security_type="REIT"),
            _profile("SUK1", security_type="Sukuk"),
        ]
        result = classify_universe(companies)
        assert result.total_instruments == 5
        assert result.total_eligible == 2
        assert result.total_excluded == 3
        assert sum(result.bucket_counts.values()) == 5
        assert result.bucket_counts["MAIN_MARKET_EQUITY"] == 2
        assert result.bucket_counts["ETF_FUND"] == 1
        assert result.bucket_counts["REIT"] == 1
        assert result.bucket_counts["SUKUK_BOND"] == 1

    def test_distinct_observed_values_captured_for_every_classified_field(self):
        companies = [_profile("1010", status="Active"), _profile("2210", status="Suspended")]
        result = classify_universe(companies)
        assert result.distinct_observed_values["status"]["Active"] == 1
        assert result.distinct_observed_values["status"]["Suspended"] == 1

    def test_empty_universe_produces_zero_counts_not_an_error(self):
        result = classify_universe([])
        assert result.total_instruments == 0
        assert result.total_eligible == 0
        assert result.eligible_symbols == []
