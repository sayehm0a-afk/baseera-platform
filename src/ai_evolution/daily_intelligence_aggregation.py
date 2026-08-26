"""E9 (part 1 of 2) of the AI Evolution Layer: pre-aggregates one
day's `RecommendationOutcome`/`AgentOpinion`/`DebateSession`/
`DiscoveredPattern` activity into a single `DailyIntelligenceSnapshot`
row, so the staff-only Intelligence Dashboard (Part 12 of the design)
reads pre-computed rows instead of live-computing aggregates on every
page load.

Mirrors `daily_reflection.generate_daily_reflection()`'s exact query
shape (`func.date(RecommendationOutcome.evaluated_at) == snapshot_date`,
one row per date, idempotent upsert) -- this module is a differently
-shaped aggregation over the same underlying data, not a duplicate of
that one's purpose (that one writes prose findings/suggestions for a
human to read; this one writes structured numbers for a dashboard to
chart).

Calibration error reuses `confidence_calibration.expected_calibration_error`
verbatim -- the same bucket-count-weighted ECE formula E3 already
established for (confidence, binary_label) pairs, not a second
implementation.

Non-negotiable per Part 14 of the design: `failed_count` is always
computed and stored, never filtered out by an opt-in flag -- there is
no parameter on this function that can suppress it.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.ai_evolution.confidence_calibration import expected_calibration_error
from src.domain.models import (
    AgentOpinion,
    DailyIntelligenceSnapshot,
    DebateSession,
    DiscoveredPattern,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)

DEFAULT_PATTERN_LIMIT = 5

_SUCCESS = RecommendationOutcomeStatus.SUCCESSFUL
_FAILURE = RecommendationOutcomeStatus.FAILED
_TERMINAL = (_SUCCESS, _FAILURE)


def _outcome_rows(session: Session, snapshot_date: date) -> List[Tuple[RecommendationSnapshot, RecommendationOutcome]]:
    return (
        session.query(RecommendationSnapshot, RecommendationOutcome)
        .join(RecommendationOutcome, RecommendationOutcome.snapshot_id == RecommendationSnapshot.id)
        .filter(func.date(RecommendationOutcome.evaluated_at) == snapshot_date)
        .all()
    )


def _sector_breakdown(
    session: Session, rows: List[Tuple[RecommendationSnapshot, RecommendationOutcome]]
) -> Optional[Dict]:
    decisive = [(s, o) for s, o in rows if o.status in _TERMINAL]
    if not decisive:
        return None

    stock_ids = {snapshot.stock_id for snapshot, _ in decisive}
    sector_by_stock_id = {row.id: row.sector for row in session.query(Stock).filter(Stock.id.in_(stock_ids)).all()}

    grouped: Dict[str, List[bool]] = defaultdict(list)
    for snapshot, outcome in decisive:
        sector = sector_by_stock_id.get(snapshot.stock_id) or "Unknown"
        grouped[sector].append(outcome.status is _SUCCESS)

    return {
        sector: {"count": len(labels), "win_rate": sum(labels) / len(labels)} for sector, labels in grouped.items()
    }


def _pattern_summary(pattern: DiscoveredPattern) -> Dict:
    return {
        "condition_description": pattern.condition_description,
        "win_rate": float(pattern.win_rate),
        "sample_size": pattern.sample_size,
        "p_value": float(pattern.p_value) if pattern.p_value is not None else None,
    }


def _best_and_worst_patterns(session: Session, limit: int) -> Tuple[Optional[List[Dict]], Optional[List[Dict]]]:
    """Best/worst are always disjoint -- `worst` is drawn only from
    whatever remains after `best` is taken, so a small pattern set
    (fewer than `2 * limit` rows) never shows the same pattern in both
    lists."""
    valid = session.query(DiscoveredPattern).filter_by(still_valid=True).all()
    if not valid:
        return None, None

    ordered = sorted(valid, key=lambda p: float(p.win_rate), reverse=True)
    best = ordered[:limit]
    remaining = ordered[limit:]
    worst = list(reversed(remaining[-limit:])) if remaining else []

    return [_pattern_summary(p) for p in best], [_pattern_summary(p) for p in worst] if worst else None


def _agent_panel_stats(session: Session, snapshot_date: date) -> Tuple[int, int, Optional[float]]:
    panel_snapshot_ids = {
        row.snapshot_id
        for row in (
            session.query(AgentOpinion.snapshot_id)
            .join(RecommendationSnapshot, RecommendationSnapshot.id == AgentOpinion.snapshot_id)
            .filter(func.date(RecommendationSnapshot.evaluated_at) == snapshot_date)
            .distinct()
            .all()
        )
    }
    debate_snapshot_ids = {
        row.snapshot_id
        for row in (
            session.query(DebateSession.snapshot_id)
            .join(RecommendationSnapshot, RecommendationSnapshot.id == DebateSession.snapshot_id)
            .filter(func.date(RecommendationSnapshot.evaluated_at) == snapshot_date)
            .all()
        )
    }
    panel_count = len(panel_snapshot_ids)
    debate_count = len(debate_snapshot_ids)
    agreement_rate = (panel_count - debate_count) / panel_count if panel_count > 0 else None
    return panel_count, debate_count, agreement_rate


def _apply_computed_fields(snapshot: DailyIntelligenceSnapshot, **fields) -> None:
    for name, value in fields.items():
        setattr(snapshot, name, value)


def aggregate_daily_intelligence(
    session: Session,
    snapshot_date: Optional[date] = None,
    pattern_limit: int = DEFAULT_PATTERN_LIMIT,
) -> DailyIntelligenceSnapshot:
    """Aggregates `snapshot_date` (default: yesterday, UTC -- the same
    default `generate_daily_reflection` uses, since a day's forward
    evaluations only finish landing after it ends) and writes/updates
    the corresponding `DailyIntelligenceSnapshot` row. Idempotent:
    re-running for an already-aggregated day updates that row's
    numbers rather than creating a duplicate.

    Race-safe across concurrent callers for the same `snapshot_date`
    (production evidence, 2026-08-26: every one of this process's
    Gunicorn workers runs its own independent
    `DailyIntelligenceAggregationScheduler` instance -- see
    scheduler.py -- so two or more can call this function for the same
    date within milliseconds of each other, e.g. right after a
    deploy). The read-then-insert below is not by itself atomic, so on
    a genuine race the loser's INSERT raises IntegrityError against
    `uq_daily_intelligence_snapshot_date` -- caught here and turned
    into what this function's own docstring already promises for a
    duplicate: an UPDATE of the winner's row with this call's freshly
    computed numbers, never a surfaced error and never a second row."""
    snapshot_date = snapshot_date or (datetime.now(timezone.utc).date() - timedelta(days=1))

    rows = _outcome_rows(session, snapshot_date)
    successful_count = sum(1 for _, o in rows if o.status is _SUCCESS)
    failed_count = sum(1 for _, o in rows if o.status is _FAILURE)
    partial_count = sum(1 for _, o in rows if o.status is RecommendationOutcomeStatus.PARTIAL)
    expired_count = sum(1 for _, o in rows if o.status is RecommendationOutcomeStatus.EXPIRED)
    decisive_count = successful_count + failed_count
    win_rate = successful_count / decisive_count if decisive_count > 0 else None

    pairs = [(float(s.confidence_score), 1 if o.status is _SUCCESS else 0) for s, o in rows if o.status in _TERMINAL]
    calibration_error = expected_calibration_error(pairs)

    sector_breakdown = _sector_breakdown(session, rows)
    best_patterns, worst_patterns = _best_and_worst_patterns(session, pattern_limit)
    panel_count, debate_count, agreement_rate = _agent_panel_stats(session, snapshot_date)

    computed_fields = dict(
        recommendations_evaluated=len(rows),
        successful_count=successful_count,
        failed_count=failed_count,
        partial_count=partial_count,
        expired_count=expired_count,
        win_rate=win_rate,
        calibration_error=calibration_error,
        agent_panel_snapshot_count=panel_count,
        agent_debate_count=debate_count,
        agent_agreement_rate=agreement_rate,
        best_patterns=best_patterns,
        worst_patterns=worst_patterns,
        sector_breakdown=sector_breakdown,
    )

    snapshot = session.query(DailyIntelligenceSnapshot).filter_by(snapshot_date=snapshot_date).one_or_none()
    is_new = snapshot is None
    if is_new:
        snapshot = DailyIntelligenceSnapshot(snapshot_date=snapshot_date)
        session.add(snapshot)
    _apply_computed_fields(snapshot, **computed_fields)

    if is_new:
        try:
            session.commit()
        except IntegrityError as exc:
            # Only fall back to "a concurrent caller already committed
            # this snapshot_date" for that specific constraint -- any
            # other IntegrityError on this insert is a genuinely
            # different failure and must keep surfacing as itself, not
            # be masked by a confusing NoResultFound from re-querying a
            # row that was never actually written.
            if "snapshot_date" not in str(exc.orig).lower():
                raise
            session.rollback()
            snapshot = session.query(DailyIntelligenceSnapshot).filter_by(snapshot_date=snapshot_date).one()
            _apply_computed_fields(snapshot, **computed_fields)
            session.commit()
    else:
        session.commit()

    return snapshot
