"""Phase 3 area 4: activates the previously-dead sector-rotation input
(`SectorRotationScoreContributor` in
src.analysis.decision.contributors.external_factor_contributors --
confirmed by the Phase 2 audit to be registered at weight 0.01 but to
always read `None` in production, since nothing ever populated
`context.extra["sector_rotation"]`).

Computes this stock's own trailing-return against the average trailing
return of its real Tadawul sector peers (`Stock.sector`, already
ingested), using only PriceBar rows already in the database -- no new
SAHMK calls, no new indicator registry entry. Deliberately the
smallest correct data flow: two DB queries (peer ids, then one batched
bar query for all peers), no per-symbol N+1 fan-out.

No look-ahead bias: every bar used is whatever is already present as
of `df`'s own cutoff (the same `df` build_analysis_context already
loaded for this stock's own technical analysis) -- this module reads
no bar dated after that.

Honest degradation, never fabricated: returns the "not computed" state
(every field None/False) when the sector is unclassified, this stock's
own history is too short, or fewer than `MIN_PEER_COUNT` peers have
both enough history and a recent-enough latest bar. A stale peer (its
own most recent bar older than `MAX_STALENESS_DAYS`) is excluded from
the peer average entirely, not counted as zero-return.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import fmean
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Stock, Timeframe

LOOKBACK_DAYS = 20
MIN_PEER_COUNT = 3
MAX_PEER_COUNT = 40
MAX_STALENESS_DAYS = 5.0
_UNCLASSIFIED_SECTORS = {None, "", "Unclassified"}

# Disclosed, not-yet-empirically-calibrated normalization -- maps a
# +/-10 percentage-point return gap against the sector peer average
# onto the contributor's expected +/-1.0 input range, the same
# "conservative placeholder" disclosure convention
# publication_gate.py's own liquidity gate already uses for an
# unvalidated threshold.
_RELATIVE_STRENGTH_NORMALIZATION_PCT = 10.0


@dataclass(frozen=True)
class SectorStrengthResult:
    sector_name: Optional[str]
    sector_strength_score: Optional[float]
    stock_vs_sector_relative_strength: Optional[float]
    sector_data_timestamp: Optional[datetime]
    sector_strength_used: bool


_NOT_COMPUTED = SectorStrengthResult(
    sector_name=None, sector_strength_score=None, stock_vs_sector_relative_strength=None,
    sector_data_timestamp=None, sector_strength_used=False,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def _trailing_return_pct(df: pd.DataFrame, lookback_days: int) -> Optional[float]:
    if len(df) < lookback_days + 1:
        return None
    start_close = float(df["close"].iloc[-(lookback_days + 1)])
    end_close = float(df["close"].iloc[-1])
    if start_close == 0:
        return None
    return (end_close / start_close - 1.0) * 100.0


def _peer_returns_and_timestamps(
    session: Session, peer_stock_ids: List[int], lookback_days: int, now: datetime
) -> tuple:
    """One batched query for every peer's bars, grouped in Python --
    the whole point of this helper is issuing exactly one PriceBar
    query regardless of how many peers there are, not one per peer."""
    rows = (
        session.query(PriceBar.stock_id, PriceBar.timestamp, PriceBar.close)
        .filter(PriceBar.stock_id.in_(peer_stock_ids), PriceBar.timeframe == Timeframe.ONE_DAY)
        .order_by(PriceBar.stock_id.asc(), PriceBar.timestamp.asc())
        .all()
    )
    by_stock: Dict[int, List[tuple]] = {}
    for stock_id, timestamp, close in rows:
        by_stock.setdefault(stock_id, []).append((timestamp, float(close)))

    returns: List[float] = []
    latest_timestamps: List[datetime] = []
    for bars in by_stock.values():
        if len(bars) < lookback_days + 1:
            continue
        latest_ts = _as_utc(bars[-1][0])
        age_days = (now - latest_ts).total_seconds() / 86400.0
        if age_days > MAX_STALENESS_DAYS:
            continue
        start_close = bars[-(lookback_days + 1)][1]
        end_close = bars[-1][1]
        if start_close == 0:
            continue
        returns.append((end_close / start_close - 1.0) * 100.0)
        latest_timestamps.append(latest_ts)
    return returns, latest_timestamps


def compute_sector_strength(
    session: Session, stock: Stock, df: pd.DataFrame, lookback_days: int = LOOKBACK_DAYS
) -> SectorStrengthResult:
    sector = stock.sector
    if sector in _UNCLASSIFIED_SECTORS:
        return _NOT_COMPUTED

    own_return_pct = _trailing_return_pct(df, lookback_days)
    if own_return_pct is None:
        return SectorStrengthResult(
            sector_name=sector, sector_strength_score=None, stock_vs_sector_relative_strength=None,
            sector_data_timestamp=None, sector_strength_used=False,
        )
    own_latest_ts = _as_utc(df.index.max())
    now = datetime.now(timezone.utc)
    if (now - own_latest_ts).total_seconds() / 86400.0 > MAX_STALENESS_DAYS:
        return SectorStrengthResult(
            sector_name=sector, sector_strength_score=None, stock_vs_sector_relative_strength=None,
            sector_data_timestamp=None, sector_strength_used=False,
        )

    peer_ids = [
        row[0]
        for row in session.query(Stock.id)
        .filter(Stock.sector == sector, Stock.id != stock.id)
        .limit(MAX_PEER_COUNT)
        .all()
    ]
    if len(peer_ids) < MIN_PEER_COUNT:
        return SectorStrengthResult(
            sector_name=sector, sector_strength_score=None, stock_vs_sector_relative_strength=None,
            sector_data_timestamp=None, sector_strength_used=False,
        )

    peer_returns, peer_timestamps = _peer_returns_and_timestamps(session, peer_ids, lookback_days, now)
    if len(peer_returns) < MIN_PEER_COUNT:
        return SectorStrengthResult(
            sector_name=sector, sector_strength_score=None, stock_vs_sector_relative_strength=None,
            sector_data_timestamp=None, sector_strength_used=False,
        )

    peer_avg_return = fmean(peer_returns)
    sector_strength_score = round(_clamp(50.0 + peer_avg_return * 2.0, 0.0, 100.0), 1)
    relative_strength = round(
        _clamp((own_return_pct - peer_avg_return) / _RELATIVE_STRENGTH_NORMALIZATION_PCT, -1.0, 1.0), 3
    )
    # The oldest "latest bar" among everything actually used -- the
    # honest freshness bound for this composite, not the newest.
    data_timestamp = min([own_latest_ts, *peer_timestamps])

    return SectorStrengthResult(
        sector_name=sector,
        sector_strength_score=sector_strength_score,
        stock_vs_sector_relative_strength=relative_strength,
        sector_data_timestamp=data_timestamp,
        sector_strength_used=True,
    )
