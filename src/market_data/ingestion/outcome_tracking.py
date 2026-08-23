"""OHLCV persistence / post-signal outcome-tracking fix (2026-08-23):
the symbol universe `IngestionScheduler`'s `historical_ohlcv` job covers
must not depend solely on `Stock.is_active` (a general "is this a
tradeable Saudi equity" flag owned by `universe_policy`/`sync_symbols`,
unrelated to whether a symbol has an outstanding Decision V2 signal
awaiting evaluation).

Root cause (documented in full in the accompanying PR description):
`IngestionScheduler._resolve_target_symbols()` unions the configured
seed list with every currently `is_active=True` Stock -- which covers
the vast majority of the real universe correctly, but carries no
explicit guarantee that a symbol with a still-`PENDING`
`DecisionV2Outcome` keeps receiving OHLCV updates if that symbol's
active status ever changes, and gives no visibility when a signal's
post-signal price history silently stays empty. This module adds that
explicit guarantee and that visibility -- it does not replace, gate, or
duplicate anything scoring/threshold/decision-related; it is a pure,
read-only query layer over the already-existing `DecisionV2Outcome`/
`DecisionV2Snapshot`/`PriceBar` tables (no new table, no migration).
"""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, PriceBar, Stock, Timeframe


def pending_signal_symbols(session: Session) -> List[str]:
    """Every distinct symbol with at least one still-`PENDING`
    `DecisionV2Outcome` -- the exact "unresolved signal" universe the
    OHLCV job must keep covering regardless of `Stock.is_active`.
    `DecisionV2Outcome.symbol` is already denormalized onto the row
    (see that model's docstring), so this needs no join."""
    rows = (
        session.query(DecisionV2Outcome.symbol)
        .filter(DecisionV2Outcome.status == DecisionV2OutcomeStatus.PENDING)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def oldest_pending_signal_decision_timestamp(session: Session) -> Optional[datetime]:
    """The `decision_timestamp` of the longest-outstanding still-PENDING
    signal -- observability only (Phase 9's `OLDEST_PENDING_SIGNAL`),
    never used to gate or alter any evaluation."""
    result = (
        session.query(func.min(DecisionV2Snapshot.decision_timestamp))
        .join(DecisionV2Outcome, DecisionV2Outcome.decision_v2_snapshot_id == DecisionV2Snapshot.id)
        .filter(DecisionV2Outcome.status == DecisionV2OutcomeStatus.PENDING)
        .scalar()
    )
    return result


def pending_signals_with_zero_post_signal_bars(session: Session) -> List[Dict]:
    """Direct, always-accurate diagnostic (not derived from any
    ingestion job's own bookkeeping, which the root-cause investigation
    found can report `status=success` while silently making zero
    progress for an already-tracked symbol -- see
    `ingest_historical_ohlcv.py`'s `zero_progress` dict, which only
    ever fires for a symbol with zero bars *ever*, not zero *new*
    bars). For every still-PENDING `DecisionV2Outcome`, checks whether
    any real `PriceBar` exists with a timestamp after the signal's own
    `decision_timestamp` -- if none does, that signal cannot yet be
    evaluated no matter how much calendar time has passed, and this is
    the exact condition Phase 9 observability must surface."""
    pending = (
        session.query(DecisionV2Outcome, DecisionV2Snapshot)
        .join(DecisionV2Snapshot, DecisionV2Outcome.decision_v2_snapshot_id == DecisionV2Snapshot.id)
        .filter(DecisionV2Outcome.status == DecisionV2OutcomeStatus.PENDING)
        .all()
    )
    flagged: List[Dict] = []
    for outcome, snapshot in pending:
        has_post_signal_bar = (
            session.query(PriceBar.id)
            .filter(
                PriceBar.stock_id == snapshot.stock_id,
                PriceBar.timeframe == Timeframe.ONE_DAY,
                PriceBar.timestamp > snapshot.decision_timestamp,
            )
            .first()
            is not None
        )
        if not has_post_signal_bar:
            flagged.append(
                {
                    "symbol": outcome.symbol,
                    "decision_v2_snapshot_id": snapshot.id,
                    "decision_timestamp": snapshot.decision_timestamp,
                    "due_at": outcome.due_at,
                }
            )
    return flagged


def active_and_pending_signal_symbol_count(session: Session) -> Dict[str, int]:
    """Cheap summary counts for Phase 9 observability (`TRACKED_SYMBOLS`
    et al.) -- computed from already-indexed columns, no full-table
    scan beyond what the two queries above already do."""
    active_count = session.query(func.count(Stock.id)).filter(Stock.is_active.is_(True)).scalar() or 0
    pending_symbols = pending_signal_symbols(session)
    return {
        "active_stock_count": int(active_count),
        "pending_signal_symbol_count": len(pending_symbols),
    }
