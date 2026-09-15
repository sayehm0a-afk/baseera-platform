"""Real, per-symbol recent-failure disclosure for Smart Radar
(`GET /api/v1/radar/...`).

Real-world evidence (owner, 2026-09-15): symbol 1830 was shown on the
Smart Radar home screen as a fresh BUY_CANDIDATE ("مناسب الآن") with a
recalculated, lower entry zone and stop-loss, while the SAME symbol's
signal from earlier the same day had already had its stop-loss breached
by real market price. `DecisionEngineV2`/`get_decision_v2` recompute a
decision from scratch against the *current* price on every call (by
design -- see that route's own docstring), so a symbol whose price keeps
falling can be re-quoted as a "new" buy opportunity indefinitely, with
nothing on the card linking it back to its own recently-failed signal.

This module adds a third, independent disclosure -- unrelated to
`sector_reliability` (which is about the sector's aggregate history, not
this exact symbol's own recent signals) -- surfacing the most recent
STOP_LOSS_HIT / INVALIDATED / negative-EXPIRED `DecisionV2Outcome` for
this exact symbol within a short lookback window. It never touches
ranking, the decision itself, or entry/stop computation -- purely a
disclosure layered on top, mirroring `sector_reliability`'s own
"disclosure, not a new decision rule" boundary.

ENTRY_NEVER_TRIGGERED/PENDING/CANCELLED/DATA_UNAVAILABLE/PARTIAL/target
hits are deliberately excluded -- none of those represent this symbol
having recently failed a real trader.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus

# Same near-term horizon rationale as sector_reliability's own
# DEFAULT_EVALUATION_HORIZON_DAYS -- a beginner reading today's card cares
# about "did this exact stock just fail," not a stale event from months
# ago that later market action has already superseded.
DEFAULT_LOOKBACK_DAYS = 14

_NEGATIVE_STATUSES = frozenset(
    {DecisionV2OutcomeStatus.STOP_LOSS_HIT, DecisionV2OutcomeStatus.INVALIDATED}
)

_STATUS_LABELS_AR = {
    DecisionV2OutcomeStatus.STOP_LOSS_HIT: "آخر إشارة لهذا السهم اخترقت وقف الخسارة",
    DecisionV2OutcomeStatus.INVALIDATED: "آخر إشارة لهذا السهم ألغيت قبل اكتمال الدخول (كسر السعر وقف الخسارة أولاً)",
    DecisionV2OutcomeStatus.EXPIRED: "آخر إشارة لهذا السهم انتهت مدتها بخسارة دون تحقيق الهدف",
}


@dataclass(frozen=True)
class RecentSymbolOutcome:
    status: str
    label_ar: str
    occurred_at: datetime
    return_pct: Optional[float]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def compute_recent_negative_outcome_by_symbol(
    session: Session,
    symbols: Iterable[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    now: Optional[datetime] = None,
) -> Dict[str, RecentSymbolOutcome]:
    """One batched query for every symbol currently being displayed
    (mirrors `sector_reliability`'s "compute once per request" shape) --
    never N+1 per card. Keeps only the most recent qualifying outcome per
    symbol."""
    symbol_list = sorted(set(symbols))
    if not symbol_list:
        return {}

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    rows = (
        session.query(DecisionV2Outcome)
        .filter(
            DecisionV2Outcome.symbol.in_(symbol_list),
            DecisionV2Outcome.evaluated_at.isnot(None),
            DecisionV2Outcome.evaluated_at >= cutoff,
            or_(
                DecisionV2Outcome.status.in_(_NEGATIVE_STATUSES),
                (DecisionV2Outcome.status == DecisionV2OutcomeStatus.EXPIRED)
                & (DecisionV2Outcome.return_pct < 0),
            ),
        )
        .order_by(DecisionV2Outcome.evaluated_at.desc())
        .all()
    )

    result: Dict[str, RecentSymbolOutcome] = {}
    for row in rows:
        if row.symbol in result:
            continue  # already have this symbol's most recent qualifying row
        result[row.symbol] = RecentSymbolOutcome(
            status=row.status.value,
            label_ar=_STATUS_LABELS_AR.get(row.status, "آخر إشارة لهذا السهم لم تحقق النتيجة المتوقعة"),
            occurred_at=_as_utc(row.evaluated_at),
            return_pct=float(row.return_pct) if row.return_pct is not None else None,
        )
    return result


def recent_negative_outcome_for_symbol(
    outcome_by_symbol: Dict[str, RecentSymbolOutcome], symbol: str
) -> Optional[RecentSymbolOutcome]:
    return outcome_by_symbol.get(symbol)
