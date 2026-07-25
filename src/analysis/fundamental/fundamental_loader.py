"""Bridges the domain layer (FundamentalSnapshot, M2.3) to the
pure-computation fundamental analysis layer. This is the only module
in src/analysis/fundamental/ that touches a database session -- every
ratio function downstream is DB-agnostic.
"""

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from src.analysis.fundamental.types import FundamentalFacts
from src.domain.models import FundamentalSnapshot, PeriodType


def _to_facts(snapshot: FundamentalSnapshot) -> FundamentalFacts:
    return FundamentalFacts(
        stock_id=snapshot.stock_id,
        period_type=snapshot.period_type.value,
        fiscal_period_end=snapshot.fiscal_period_end,
        revenue=float(snapshot.revenue),
        gross_profit=float(snapshot.gross_profit) if snapshot.gross_profit is not None else None,
        net_income=float(snapshot.net_income),
        total_assets=float(snapshot.total_assets),
        total_liabilities=float(snapshot.total_liabilities),
        total_equity=float(snapshot.total_equity),
        current_assets=float(snapshot.current_assets),
        current_liabilities=float(snapshot.current_liabilities),
        inventory=float(snapshot.inventory) if snapshot.inventory is not None else None,
        cash_and_equivalents=(
            float(snapshot.cash_and_equivalents) if snapshot.cash_and_equivalents is not None else None
        ),
        total_debt=float(snapshot.total_debt) if snapshot.total_debt is not None else None,
        shares_outstanding=int(snapshot.shares_outstanding),
        eps=float(snapshot.eps),
        dividend_per_share=float(snapshot.dividend_per_share),
    )


def load_fundamental_snapshots(
    session: Session,
    stock_id: int,
    period_type: PeriodType,
    limit: int = 8,
    as_of: Optional[date] = None,
) -> List[FundamentalFacts]:
    """Query FundamentalSnapshot rows for one stock/period type, most
    recent fiscal period first, converted to the pure FundamentalFacts
    shape.

    Numeric(...) columns are stored as Decimal for storage precision;
    they are converted to float here, at this single boundary, for the
    same reason ohlcv_loader.py converts PriceBar's Decimal columns to
    float64: every ratio downstream is a statistical/approximate
    computation, not a settlement-grade calculation.

    Returns an empty list, not an exception, if no snapshots match --
    a stock with no reported fundamentals yet is a valid, expected
    state, not an error.

    `as_of` is optional and additive (added for the Backtesting &
    Calibration Engine's anti-look-ahead requirement) -- omitted, this
    function's behavior is unchanged from before that milestone: the N
    most recent snapshots regardless of date, correct for every
    existing caller (the live /fundamentals and /recommendation routes,
    which always want "as of right now"). When given, only snapshots
    with `fiscal_period_end <= as_of` are eligible, so a backtest
    evaluating a historical date never sees a fiscal period that, from
    that date's point of view, hadn't happened yet. This alone is a
    conservative approximation, not exact filing-date accuracy -- see
    src/backtesting/data_access.py for the additional reporting-lag
    buffer applied on top of this filter.
    """
    query = session.query(FundamentalSnapshot).filter(
        FundamentalSnapshot.stock_id == stock_id,
        FundamentalSnapshot.period_type == period_type,
    )
    if as_of is not None:
        query = query.filter(FundamentalSnapshot.fiscal_period_end <= as_of)
    query = query.order_by(FundamentalSnapshot.fiscal_period_end.desc()).limit(limit)
    return [_to_facts(snapshot) for snapshot in query.all()]


def load_latest_fundamental_facts(
    session: Session, stock_id: int, period_type: PeriodType
) -> Optional[FundamentalFacts]:
    """Convenience wrapper: the single most recent snapshot, or None."""
    snapshots = load_fundamental_snapshots(session, stock_id, period_type, limit=1)
    return snapshots[0] if snapshots else None
