"""P0 SAHMK quota architecture repair (2026-08-25): deterministic OHLCV
refresh tiering + fair background rotation.

Real, verified problem this closes: the active market universe is
~384 symbols; the real upstream SAHMK daily quota is ~100 requests/day
(see src.market_data.config.get_sahmk_max_requests_per_day's own
docstring for the evidence). A full-market daily refresh is therefore
structurally impossible -- what matters is refreshing the highest-value
symbols first, every day, and rotating fairly through the rest so no
symbol is starved forever.

Five tiers, most-protected first:

  TIER 0 -- active positions: symbols with a PENDING DecisionV2Outcome
    whose entry has already triggered (entry_triggered=True). A real,
    already-open position -- the single most consumer-critical thing
    to keep monitoring (target/stop tracking).
  TIER 1 -- pending, not-yet-triggered signals: symbols with a PENDING
    DecisionV2Outcome that has not yet triggered (still WAIT_FOR_ENTRY-
    relevant). Only BUY-family decisions ever get a DecisionV2Outcome
    row at all (see that model's own docstring) -- WATCH/HOLD/REJECT
    open no position and have nothing here to protect.
  TIER 2 -- live Radar candidates: symbols with a still-live (not
    superseded) RadarOpportunity from the most recent scan. Zero
    additional provider cost to identify -- a pure read of
    already-persisted, already-computed data.
  TIER 3 -- last scan's evaluated universe: every symbol Decision V2
    actually evaluated in the most recent successful MarketScanRun,
    whether or not it became a RadarOpportunity. Also zero additional
    provider cost.
  TIER 4 -- everything else: the general background universe,
    deterministically rotated oldest-current-bar-first (Section 6's
    fair-rotation requirement) so no symbol is stuck at the tail
    forever.

Tiers 0+1 together are "the critical refresh set" -- small, bounded,
run at priority=CRITICAL with a tight date range (see
ingest_historical_ohlcv.py's own incremental-catch-up behavior, which
already fetches only from the latest ingested day forward). Tiers 2-4
are "the background refresh set" -- run at priority=BACKGROUND,
protected from the critical and live-scan reserves by
SahmkRateLimiter's own acquire() cutoffs, never the other way around.

A symbol is placed in exactly one tier (its highest) -- see
`build_priority_plan`'s own dedup contract.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    MarketScanRun,
    MarketScanStatus,
    PriceBar,
    RadarOpportunity,
    Stock,
    Timeframe,
)


def tier0_active_position_symbols(session: Session) -> List[str]:
    """Every distinct symbol with a PENDING DecisionV2Outcome whose
    entry has already triggered -- a real, currently-open position."""
    rows = (
        session.query(DecisionV2Outcome.symbol)
        .filter(
            DecisionV2Outcome.status == DecisionV2OutcomeStatus.PENDING,
            DecisionV2Outcome.entry_triggered.is_(True),
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def tier1_pending_entry_symbols(session: Session) -> List[str]:
    """Every distinct symbol with a PENDING DecisionV2Outcome whose
    entry has not yet triggered -- still WAIT_FOR_ENTRY-relevant, one
    rank below an already-open position."""
    rows = (
        session.query(DecisionV2Outcome.symbol)
        .filter(
            DecisionV2Outcome.status == DecisionV2OutcomeStatus.PENDING,
            DecisionV2Outcome.entry_triggered.is_(False),
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def tier2_live_radar_candidate_symbols(session: Session) -> List[str]:
    """Every distinct symbol with a still-live (superseded_by_id IS
    NULL) RadarOpportunity -- "current top Radar/Decision candidates,"
    read at zero additional provider cost from already-persisted scan
    output (never re-runs Stage 1, never makes a new request merely to
    populate this tier)."""
    rows = (
        session.query(RadarOpportunity.symbol)
        .filter(RadarOpportunity.superseded_by_id.is_(None))
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def tier3_last_scan_universe_symbols(session: Session) -> List[str]:
    """Every distinct symbol Decision V2 actually evaluated in the most
    recent successful MarketScanRun -- broader than Tier 2 (includes
    WATCH/HOLD/REJECT symbols the scan looked at but did not emit as a
    RadarOpportunity), still zero additional provider cost."""
    latest_run_id = (
        session.query(func.max(MarketScanRun.id))
        .filter(MarketScanRun.status == MarketScanStatus.SUCCESS)
        .scalar()
    )
    if latest_run_id is None:
        return []
    rows = (
        session.query(DecisionV2Snapshot.symbol)
        .filter(DecisionV2Snapshot.scan_run_id == latest_run_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def _dedup_preserve_order(symbols: List[str]) -> List[str]:
    return list(dict.fromkeys(symbols))


@dataclass
class OhlcvPriorityPlan:
    """A symbol appears in exactly one of these lists -- its highest
    tier. `critical_symbols` is tier0 + tier1 (tier0 first);
    `background_symbols` is tier2 + tier3 + the fairly-rotated
    remainder of `base_symbols`, with every critical-tier symbol
    excluded."""

    tier0: List[str] = field(default_factory=list)
    tier1: List[str] = field(default_factory=list)
    tier2: List[str] = field(default_factory=list)
    tier3: List[str] = field(default_factory=list)
    tier4: List[str] = field(default_factory=list)

    @property
    def critical_symbols(self) -> List[str]:
        return _dedup_preserve_order(self.tier0 + self.tier1)

    @property
    def background_symbols(self) -> List[str]:
        return _dedup_preserve_order(self.tier2 + self.tier3 + self.tier4)


def _last_successful_bar_dates(session: Session, stock_ids: List[int]) -> Dict[int, datetime]:
    """stock_id -> most recent daily PriceBar timestamp, for exactly
    the given stock_ids (avoids scanning the whole PriceBar table when
    only a bounded symbol set is being rotated). A stock_id absent from
    the returned dict has never had a single bar ingested -- callers
    must treat that as "oldest possible" (sorts first), not as an
    error."""
    if not stock_ids:
        return {}
    rows = (
        session.query(PriceBar.stock_id, func.max(PriceBar.timestamp))
        .filter(PriceBar.timeframe == Timeframe.ONE_DAY, PriceBar.stock_id.in_(stock_ids))
        .group_by(PriceBar.stock_id)
        .all()
    )
    return {stock_id: ts for stock_id, ts in rows}


def _fair_rotation_order(session: Session, symbols: List[str]) -> List[str]:
    """Deterministic, starvation-resistant ordering for `symbols`:
    oldest-successful-current-bar-first (a symbol with no bar at all
    sorts as if its "last bar" were the earliest possible instant, i.e.
    first), tie-broken by symbol ascending. No in-memory-only cursor,
    no persisted new schema state -- fully derived from PriceBar on
    every call, so it is restart-safe and multi-worker-safe by
    construction (every worker computes the identical order from the
    same durable data)."""
    if not symbols:
        return []
    stock_rows = (
        session.query(Stock.id, Stock.symbol).filter(Stock.symbol.in_(symbols)).all()
    )
    symbol_to_stock_id = {symbol: stock_id for stock_id, symbol in stock_rows}
    stock_ids = list(symbol_to_stock_id.values())
    last_bar_dates = _last_successful_bar_dates(session, stock_ids)

    def sort_key(symbol: str):
        stock_id = symbol_to_stock_id.get(symbol)
        last_bar_at = last_bar_dates.get(stock_id) if stock_id is not None else None
        # None (never ingested, or Stock row not found yet) sorts as
        # the oldest possible value -- refreshed before every symbol
        # that has at least one real bar on record.
        return (last_bar_at is not None, last_bar_at, symbol)

    return sorted(_dedup_preserve_order(symbols), key=sort_key)


def build_priority_plan(session: Session, base_symbols: List[str]) -> OhlcvPriorityPlan:
    """The single entry point ingest scheduling should call: computes
    all five tiers and returns them with the dedup contract already
    applied (a symbol keeps only its highest tier). `base_symbols` is
    the existing "resolve target symbols" universe (configured seed +
    discovered active Stock rows) -- Tier 4 is exactly this set minus
    everything already claimed by tiers 0-3, fairly rotated."""
    tier0 = tier0_active_position_symbols(session)
    tier1 = [s for s in tier1_pending_entry_symbols(session) if s not in set(tier0)]

    already_critical = set(tier0) | set(tier1)
    tier2 = [s for s in tier2_live_radar_candidate_symbols(session) if s not in already_critical]

    already_tier_0_1_2 = already_critical | set(tier2)
    tier3 = [s for s in tier3_last_scan_universe_symbols(session) if s not in already_tier_0_1_2]

    already_tiered = already_tier_0_1_2 | set(tier3)
    remainder = [s for s in base_symbols if s not in already_tiered]
    tier4 = _fair_rotation_order(session, remainder)

    return OhlcvPriorityPlan(tier0=tier0, tier1=tier1, tier2=tier2, tier3=tier3, tier4=tier4)


def estimate_max_background_refresh_age_days(
    background_symbol_count: int, background_requests_per_day: int
) -> Optional[float]:
    """How many days a Tier 4 background symbol can go, worst case,
    before its turn comes back around under fair rotation -- pure
    arithmetic (ceil(background_symbol_count / background_requests_per_day)),
    used for Section 6/19's MAX_BACKGROUND_REFRESH_AGE reporting. None
    if background_requests_per_day is 0 (rotation never advances)."""
    if background_requests_per_day <= 0:
        return None
    if background_symbol_count <= 0:
        return 0.0
    return background_symbol_count / background_requests_per_day
