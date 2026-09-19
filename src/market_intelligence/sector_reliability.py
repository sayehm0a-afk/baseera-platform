"""Real, honest per-sector historical reliability for the personal
"أفضل فرص المضاربة الآن" screen (`GET /market/personal/top-opportunities`).

Beginner traders are the intended audience for that screen and, per the
product owner (2026-09-15), the ones most likely to rely on it blindly.
Two real findings from the already-tracked `RecommendationOutcome` data
motivate this module:

1. Sector performance is highly bifurcated -- e.g. Banks/Materials have
   shown 70-100% real win rates while Energy/Telecommunication Services
   have shown near-0% win rates, over the same evaluation horizon.
2. `confidence_score` alone does *not* reliably track real accuracy (a
   separate, still-open calibration problem) -- so a beginner reading
   only the confidence percentage on a card can be misled.

This module adds a third, independent signal -- the sector's own real,
historical win rate -- computed fresh from the exact same outcome
population `personal_performance.compute_personal_performance_dashboard`
already uses (`fetch_live_outcomes` + `TERMINAL_OUTCOME_STATUSES`), never
a separate or re-interpreted data source. It deliberately does NOT touch
`personal_scan.select_top_opportunities`'s ranking or Decision Engine
V2's BUY/HOLD/REJECT decision at all -- this is a disclosure layered on
top of an unchanged decision, not a new decision rule.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.ai_evolution.personal_performance import (
    MIN_GROUP_SAMPLE_SIZE,
    TERMINAL_OUTCOME_STATUSES,
    fetch_live_outcomes,
    to_evaluation_outcome,
)
from src.backtesting.metrics import breakdown_by
from src.domain.sector_labels import sector_label_ar
from src.market_data.caching.ttl_cache import _MISSING, TTLCache

# `fetch_live_outcomes` runs an unbounded 3-way join with no LIMIT, and
# every call into this module re-runs it from scratch -- expensive, and
# unnecessary, since this is a market-wide aggregate (no per-user/
# per-request parameter -- see the function signature below) that in
# practice changes at most once per trading day, as new
# `RecommendationOutcome` rows resolve. 10 minutes is comfortably inside
# that refresh window and well above this codebase's own short-lived
# live-quote TTLs (`QUOTE_CACHE_TTL_SECONDS`/`MARKET_STATUS_CACHE_TTL_
# SECONDS` = 15s in src.market_data.polygon/sahmk.service), matching
# this data's much slower true rate of change -- the same reasoning
# those TTLs use, applied to a slower-moving signal.
#
# 2026-09-19 audit: this was invoked on every `GET /api/v1/radar` (list)
# and `GET /api/v1/radar/opportunities/{id}` call. `TTLCache`'s plain
# sync `get`/`set` are used here (not the async single-flight
# `get_or_compute`) since every caller of this function is a sync route
# handler; the rare race between two concurrent cache-miss requests
# both recomputing is harmless (same eventual value), unlike the
# metered-vendor-call case `get_or_compute` protects elsewhere.
_SECTOR_RELIABILITY_CACHE_TTL_SECONDS = 600.0
_sector_reliability_cache = TTLCache(default_ttl_seconds=_SECTOR_RELIABILITY_CACHE_TTL_SECONDS)

RELIABILITY_HIGH = "HIGH"
RELIABILITY_MODERATE = "MODERATE"
RELIABILITY_LOW = "LOW"
RELIABILITY_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Thresholds are plain real-number win-rate cutoffs, not tuned against
# this dataset -- >=60% clearly better than a coin flip, <35% clearly
# worse; the real data seen so far (Banks ~74-93%, Materials ~60-100%
# vs. Energy ~0-7%, Telecom ~4-22.5%) sits comfortably on either side of
# both cutoffs, with nothing observed landing ambiguously close to them.
_HIGH_WIN_RATE_THRESHOLD = 0.60
_LOW_WIN_RATE_THRESHOLD = 0.35

# Day-trading-scale horizon -- matches this screen's own purpose (a
# same-day/near-term "امسح السوق الآن" pick, see personal_scan.py's own
# docstring), not the dashboard's longer default (7 days).
DEFAULT_EVALUATION_HORIZON_DAYS = 3

RELIABILITY_LABELS_AR = {
    RELIABILITY_HIGH: "موثوقية تاريخية عالية لهذا القطاع",
    RELIABILITY_MODERATE: "موثوقية تاريخية متوسطة لهذا القطاع",
    RELIABILITY_LOW: "موثوقية تاريخية ضعيفة لهذا القطاع -- توخَّ الحذر",
    RELIABILITY_INSUFFICIENT_DATA: "بيانات غير كافية لتقييم موثوقية هذا القطاع بعد",
}


@dataclass(frozen=True)
class SectorReliability:
    level: str
    label_ar: str
    win_rate_pct: Optional[float]
    sample_size: int


_INSUFFICIENT_DATA_RELIABILITY = SectorReliability(
    level=RELIABILITY_INSUFFICIENT_DATA,
    label_ar=RELIABILITY_LABELS_AR[RELIABILITY_INSUFFICIENT_DATA],
    win_rate_pct=None,
    sample_size=0,
)


def _classify(win_rate: float) -> str:
    if win_rate >= _HIGH_WIN_RATE_THRESHOLD:
        return RELIABILITY_HIGH
    if win_rate < _LOW_WIN_RATE_THRESHOLD:
        return RELIABILITY_LOW
    return RELIABILITY_MODERATE


def compute_sector_reliability_by_arabic_label(
    session: Session, evaluation_horizon_days: int = DEFAULT_EVALUATION_HORIZON_DAYS
) -> Dict[str, SectorReliability]:
    """Real win_rate per sector from already-tracked `RecommendationOutcome`
    data, keyed by the Arabic sector label (`sector_label_ar(Stock.sector)`)
    so a caller can look it up directly against a `DecisionV2Snapshot.
    sector_ar` value -- the two are produced from the same translation
    table and therefore always agree for any sector SAHMK reports.

    Cached for `_SECTOR_RELIABILITY_CACHE_TTL_SECONDS` (module docstring
    above) -- this is a market-wide aggregate with no per-user/
    per-request input, so the cache key is `evaluation_horizon_days`
    alone."""
    cache_key = ("sector_reliability_by_arabic_label", evaluation_horizon_days)
    cached = _sector_reliability_cache.get(cache_key)
    if cached is not _MISSING:
        return cached

    result = _compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days)
    _sector_reliability_cache.set(cache_key, result)
    return result


def _compute_sector_reliability_by_arabic_label(
    session: Session, evaluation_horizon_days: int
) -> Dict[str, SectorReliability]:
    """The real (uncached) computation -- see the public,
    cache-wrapping `compute_sector_reliability_by_arabic_label` above."""
    rows = fetch_live_outcomes(session, evaluation_horizon_days)
    terminal_rows = [row for row in rows if row[0].status in TERMINAL_OUTCOME_STATUSES]
    evaluation_outcomes = [to_evaluation_outcome(o, s, stock) for o, s, stock in terminal_rows]
    by_sector = breakdown_by(evaluation_outcomes, lambda o: o.sector) if evaluation_outcomes else {}

    result: Dict[str, SectorReliability] = {}
    for english_sector, metrics in by_sector.items():
        arabic_label = sector_label_ar(english_sector)
        if arabic_label is None:
            continue
        sample_size = metrics["evaluation_count"]
        win_rate = metrics["win_rate"]
        if sample_size < MIN_GROUP_SAMPLE_SIZE or win_rate is None:
            result[arabic_label] = SectorReliability(
                level=RELIABILITY_INSUFFICIENT_DATA,
                label_ar=RELIABILITY_LABELS_AR[RELIABILITY_INSUFFICIENT_DATA],
                win_rate_pct=None,
                sample_size=sample_size,
            )
            continue
        level = _classify(win_rate)
        result[arabic_label] = SectorReliability(
            level=level,
            label_ar=RELIABILITY_LABELS_AR[level],
            win_rate_pct=round(win_rate * 100, 1),
            sample_size=sample_size,
        )
    return result


def reliability_for_sector(
    reliability_by_sector_ar: Dict[str, SectorReliability], sector_ar: Optional[str]
) -> SectorReliability:
    if sector_ar is None:
        return _INSUFFICIENT_DATA_RELIABILITY
    return reliability_by_sector_ar.get(sector_ar, _INSUFFICIENT_DATA_RELIABILITY)
