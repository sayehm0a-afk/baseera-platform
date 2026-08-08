"""Eligible Saudi equity universe policy.

SAHMK's `/companies/` directory (src.market_data.sahmk.service.
get_company_directory) mixes every instrument type Tadawul lists --
common equities, REITs, ETFs/funds, sukuk, rights issues -- in one
undifferentiated response. The only real, confirmed fields on a
directory entry (from live SAHMK data, workflow runs
30738871790/30743446789) are: `symbol`, `name_ar`, `name_en`,
`is_etf`, `market`, `market_segment`, `security_type`, `status`.
There is no `sector` field of any name (see service.py's own
sector-unresolved warning).

This module classifies each entry using ONLY those confirmed real
fields, and does so generically: it never assumes a specific string
value ("Main Market", "ACTIVE", ...) because no live run has yet
logged what the *values* of `market`/`market_segment`/`security_type`/
`status` actually are (only that the *keys* exist).

Deliberate deny-list design, not an allow-list: an instrument is
excluded only when it POSITIVELY matches a known non-equity/inactive
marker (is_etf=True, security_type containing "reit"/"etf"/"fund"/
"sukuk"/"bond"/"right", status containing "suspend"/"delist"/
"inactive"). Everything else defaults to ELIGIBLE. An earlier
allow-list version of this policy (excluding anything that failed to
positively match "common"/"share" etc.) was caught before shipping:
tested against a plausible-but-unconfirmed real value
(security_type="Unknown-Value-ABC"), it silently excluded a normal
equity. Since the real literal strings SAHMK uses have never been
logged (see the INFO-suppression gap this same mandate also fixes),
an allow-list risks zeroing out the entire eligible universe on an
unlucky string mismatch -- exactly the kind of silent mass-exclusion
this mandate exists to prevent. A false positive here (wrongly
including something that turns out to be non-equity) is a much
smaller, more visible error than a false negative (wrongly excluding
legitimate common equities market-wide), and every non-deny-list
field mismatch still surfaces in a distinctly labeled, non-excluding
"*_UNCONFIRMED" bucket plus `distinct_observed_values`, so the real
strings become visible in the very next report and the deny-list can
be tightened once they're known -- without ever having silently
dropped real companies to get there.

Real values confirmed 2026-08-08 via GET /api/v1/admin/
market-intelligence/universe-diagnostics against the live production
SAHMK /companies/ directory: every non-sukuk instrument seen so far
has security_type="Equity" and market_segment="TASI"; every sukuk
instrument has security_type="Sukuk" and market_segment="SUKUK".

CORRECTION (same day, later): the "100 real instruments, no Nomu
indicator anywhere" observation above was itself an artifact of a real
bug in SahmkMarketDataService.get_company_directory() -- it read the
response's `count` field (this page's own size) before `total` (the
true grand total) when deciding whether more pages existed, so it
silently stopped after one 100-item page every time. A direct probe of
the same live API (bypassing that buggy logic) showed the endpoint's
real unfiltered total is 517, and `GET /companies/?market=NOMU` is a
real, working filter returning a total of 126 -- so Nomu-market
instruments do exist in SAHMK's data and were never actually excluded
by SAHMK; they were simply never fetched. That pagination bug is now
fixed. This deny-list logic (_NOMU_SEGMENT_MARKERS/_MAIN_SEGMENT_MARKERS
below) was already written to classify a real "nomu"/"parallel"
market_segment value correctly and did not need to change -- it was
only ever starved of the data to classify.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.market_data.sahmk.models import SahmkCompanyProfile

# Substrings matched case-insensitively against `security_type` to
# positively identify a plain common-equity listing. Deliberately
# narrow: an unmatched security_type is excluded (UNCLASSIFIED_TYPE),
# never assumed eligible. "equity" confirmed live in production
# (GET /api/v1/admin/market-intelligence/universe-diagnostics,
# 2026-08-08): SAHMK's real security_type for all 96 non-sukuk
# instruments in the /companies/ directory is the literal string
# "Equity", not "Common Share"/"Ordinary Shares" as originally guessed.
_COMMON_EQUITY_TYPE_MARKERS = ("common", "ordinary", "equity share", "share", "equity")
# Substrings that positively identify instrument types this policy
# always excludes, even if they also loosely match an equity marker
# above (checked first).
_REIT_TYPE_MARKERS = ("reit",)
_FUND_ETF_TYPE_MARKERS = ("etf", "fund", "mutual")
_SUKUK_BOND_TYPE_MARKERS = ("sukuk", "bond")
_RIGHTS_TYPE_MARKERS = ("right",)

# Defense-in-depth beyond security_type: the real Arabic company name
# itself spells out the instrument type for sukuk/REITs even when
# security_type doesn't match one of the markers above (root-caused
# 2026-08-08 in production -- symbols 5027/5388/5389 carry security_type
# values that didn't match _SUKUK_BOND_TYPE_MARKERS, yet their real
# name_ar is literally "صكوك ..." (sukuk ...); symbol 9300's real
# name_ar is "الواحة ريت" (Al-Waha REIT) and likewise leaked past the
# security_type check). These are real, already-present identity
# fields -- not inferred or fabricated -- so checking them is a second,
# independent confirmation signal, not a guess.
_SUKUK_NAME_MARKERS_AR = ("صك",)  # matches صك/صكوك (sukuk/sukuks)
_REIT_NAME_MARKERS_AR = ("ريت",)  # matches ريت (REIT)

_NOMU_SEGMENT_MARKERS = ("nomu", "parallel")
# "tasi" confirmed live in production (same universe-diagnostics run):
# SAHMK's real market_segment for every one of those 96 equities is
# the literal string "TASI" (Tadawul All Share Index -- the Main
# Market index code), not the generic word "Main"/"Main Market" as
# originally guessed. TASI is definitionally Main Market, never Nomu
# Parallel Market (which trades under its own "Nomu" index), so this
# is a safe, unambiguous positive marker.
_MAIN_SEGMENT_MARKERS = ("main", "tasi")

_ACTIVE_STATUS_MARKERS = ("active", "listed", "trading", "normal")
_SUSPENDED_STATUS_MARKERS = ("suspend",)
_DELISTED_STATUS_MARKERS = ("delist", "inactive", "halt")


@dataclass
class InstrumentClassification:
    symbol: str
    name_ar: Optional[str]
    name_en: Optional[str]
    is_etf: Optional[bool]
    market: Optional[str]
    market_segment: Optional[str]
    security_type: Optional[str]
    status: Optional[str]
    eligible: bool
    bucket: str
    exclusion_reason: Optional[str]


@dataclass
class UniverseClassificationResult:
    total_instruments: int
    eligible_symbols: List[str]
    classifications: List[InstrumentClassification]
    bucket_counts: Dict[str, int] = field(default_factory=dict)
    distinct_observed_values: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def total_eligible(self) -> int:
        return len(self.eligible_symbols)

    @property
    def total_excluded(self) -> int:
        return self.total_instruments - self.total_eligible


def _field(raw: Dict[str, Any], key: str) -> Optional[Any]:
    value = raw.get(key)
    return value


def _matches_any(value: Optional[str], markers: tuple) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(m in lowered for m in markers)


def _classify_one(profile: SahmkCompanyProfile) -> InstrumentClassification:
    raw = profile.raw or {}
    is_etf = _field(raw, "is_etf")
    market = _field(raw, "market")
    market_segment = _field(raw, "market_segment")
    security_type = _field(raw, "security_type")
    status = _field(raw, "status")
    name_ar = _field(raw, "name_ar")
    name_en = _field(raw, "name_en") or profile.name

    def _make(eligible: bool, bucket: str, reason: Optional[str]) -> InstrumentClassification:
        return InstrumentClassification(
            symbol=profile.symbol,
            name_ar=name_ar,
            name_en=name_en,
            is_etf=is_etf if isinstance(is_etf, bool) else None,
            market=market if isinstance(market, str) else None,
            market_segment=market_segment if isinstance(market_segment, str) else None,
            security_type=security_type if isinstance(security_type, str) else None,
            status=status if isinstance(status, str) else None,
            eligible=eligible,
            bucket=bucket,
            exclusion_reason=reason,
        )

    if is_etf is True:
        return _make(False, "ETF_FUND", f"is_etf=True (raw={raw.get('is_etf')!r})")

    if _matches_any(security_type, _REIT_TYPE_MARKERS):
        return _make(False, "REIT", f"security_type={security_type!r}")
    if _matches_any(security_type, _FUND_ETF_TYPE_MARKERS):
        return _make(False, "ETF_FUND", f"security_type={security_type!r}")
    if _matches_any(security_type, _SUKUK_BOND_TYPE_MARKERS):
        return _make(False, "SUKUK_BOND", f"security_type={security_type!r}")
    if _matches_any(security_type, _RIGHTS_TYPE_MARKERS):
        return _make(False, "RIGHTS_ISSUE", f"security_type={security_type!r}")

    # Second, independent signal on the real Arabic name -- catches the
    # real production leak where security_type alone didn't positively
    # match for some sukuk/REIT entries (see the module-level marker
    # comment above).
    if _matches_any(name_ar, _SUKUK_NAME_MARKERS_AR):
        return _make(False, "SUKUK_BOND", f"name_ar contains a sukuk marker: {name_ar!r}")
    if _matches_any(name_ar, _REIT_NAME_MARKERS_AR):
        return _make(False, "REIT", f"name_ar contains a REIT marker: {name_ar!r}")

    if _matches_any(status, _DELISTED_STATUS_MARKERS):
        return _make(False, "INACTIVE_DELISTED", f"status={status!r}")
    if _matches_any(status, _SUSPENDED_STATUS_MARKERS):
        return _make(False, "SUSPENDED", f"status={status!r}")

    # Deny-list only from here down: security_type/status not matching
    # any *exclusion* marker defaults to eligible common equity, even
    # if it also failed to positively match a known equity/active
    # marker -- see the module docstring for why an allow-list here is
    # unsafe given the real string values are still unconfirmed. The
    # mismatch is still recorded (bucket name + distinct_observed_values)
    # so it's visible, just not treated as an exclusion.
    type_confirmed_equity = _matches_any(security_type, _COMMON_EQUITY_TYPE_MARKERS)
    status_confirmed_active = _matches_any(status, _ACTIVE_STATUS_MARKERS)

    if _matches_any(market_segment, _NOMU_SEGMENT_MARKERS):
        bucket = "NOMU_EQUITY"
    elif _matches_any(market_segment, _MAIN_SEGMENT_MARKERS) or market_segment is None:
        bucket = "MAIN_MARKET_EQUITY"
    else:
        bucket = "MAIN_MARKET_EQUITY_SEGMENT_UNCONFIRMED"

    if not type_confirmed_equity:
        bucket = f"{bucket}_TYPE_UNCONFIRMED"
    if status is not None and not status_confirmed_active:
        bucket = f"{bucket}_STATUS_UNCONFIRMED"

    return _make(True, bucket, None)


def classify_universe(companies: List[SahmkCompanyProfile]) -> UniverseClassificationResult:
    """Classifies every discovered SAHMK directory entry using only
    real, confirmed raw fields. Returns the full per-symbol breakdown
    plus aggregate bucket counts and the distinct literal values seen
    per field (so a human reviewing the report can see exactly what
    strings SAHMK actually uses, without this code having guessed)."""
    classifications = [_classify_one(c) for c in companies]

    bucket_counts: Dict[str, int] = {}
    distinct_values: Dict[str, Dict[str, int]] = {
        "market": {}, "market_segment": {}, "security_type": {}, "status": {}, "is_etf": {},
    }
    for c in classifications:
        bucket_counts[c.bucket] = bucket_counts.get(c.bucket, 0) + 1
        for field_name, value in (
            ("market", c.market), ("market_segment", c.market_segment),
            ("security_type", c.security_type), ("status", c.status), ("is_etf", c.is_etf),
        ):
            key = str(value)
            distinct_values[field_name][key] = distinct_values[field_name].get(key, 0) + 1

    eligible_symbols = [c.symbol for c in classifications if c.eligible]

    return UniverseClassificationResult(
        total_instruments=len(classifications),
        eligible_symbols=eligible_symbols,
        classifications=classifications,
        bucket_counts=bucket_counts,
        distinct_observed_values=distinct_values,
    )
