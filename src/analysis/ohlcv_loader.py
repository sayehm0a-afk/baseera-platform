"""Bridges the domain layer (PriceBar, M2.1) to the pure-computation
analysis layer. This is the only module in src/analysis/ that touches
a database session -- every indicator function is DB-agnostic.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Timeframe
from src.analysis.types import REQUIRED_OHLCV_COLUMNS


def load_price_bars(
    session: Session,
    stock_id: int,
    timeframe: Timeframe,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> pd.DataFrame:
    """Query PriceBar rows for one stock/timeframe and return a
    DataFrame indexed by timestamp (ascending), with exactly the
    columns in REQUIRED_OHLCV_COLUMNS, dtype float64.

    PriceBar's open/high/low/close are stored as Decimal(18,4) for
    storage precision; they are converted to float64 here, at this
    single boundary, because every indicator downstream is a
    statistical/approximate computation (e.g. a 14-period RSI), not a
    settlement-grade calculation -- float64's ~15-17 significant digits
    is vastly more precision than the 4 decimal places PriceBar stores,
    so this conversion loses no meaningful information for this
    purpose. It must not be used for anything requiring exact decimal
    arithmetic (e.g. actual trade settlement), which is out of this
    module's scope entirely.

    Returns an empty DataFrame (same columns, zero rows) if no bars
    match -- this is a valid "no data" result, not an error. Only a
    genuine query/session failure raises.
    """
    query = session.query(PriceBar).filter(
        PriceBar.stock_id == stock_id,
        PriceBar.timeframe == timeframe,
    )
    if start is not None:
        query = query.filter(PriceBar.timestamp >= start)
    if end is not None:
        query = query.filter(PriceBar.timestamp <= end)
    query = query.order_by(PriceBar.timestamp.asc())

    bars = query.all()

    if not bars:
        return pd.DataFrame(columns=list(REQUIRED_OHLCV_COLUMNS))

    records = [
        {
            "timestamp": bar.timestamp,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
        }
        for bar in bars
    ]
    df = pd.DataFrame.from_records(records)
    df = df.set_index("timestamp")
    return df[list(REQUIRED_OHLCV_COLUMNS)]
