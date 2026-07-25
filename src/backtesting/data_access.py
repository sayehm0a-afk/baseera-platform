"""Anti-look-ahead data access for the Backtesting & Calibration Engine.

Every function here answers "what did we actually know as of this
historical date" -- the single most safety-critical property a
backtester has, and the reason this module exists on top of the
already-reusable `ohlcv_loader.load_price_bars`/
`fundamental_loader.load_fundamental_snapshots` rather than letting
BacktestingEngine query the ORM directly. Nothing here recomputes an
indicator or a ratio; it only decides what slice of already-ingested
data TechnicalAnalysisEngine/FundamentalAnalysisEngine are allowed to
see for one evaluation date, then calls them exactly as the
/technical, /fundamentals, /recommendation, and /decision routes
already do.

Two distinct data-access shapes live here, and mixing them up is the
one mistake that would silently reintroduce look-ahead bias:
  - `load_as_of_dataset()` -- backward-only, for *making* a decision.
  - `load_forward_price_path()` -- forward-looking, for *scoring* a
    decision already made (this is not leakage: evaluating what
    actually happened after a historical recommendation is the entire
    point of backtesting, as long as that forward data never flows
    back into the decision itself).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.fundamental_loader import load_fundamental_snapshots
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.recommendation.types import AnalysisContext
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.domain.models import PeriodType, PriceBar, Stock, Timeframe

# A fiscal_period_end alone is when a period *ended*, not when the
# company's results became public -- FundamentalSnapshot has no filing/
# publication-date field (see the architecture audit). This buffer is a
# documented, conservative approximation standing in for that missing
# field: a fiscal period is assumed unavailable to the market until
# this many days after it ended. 45 days comfortably covers Tadawul's
# typical quarterly reporting window; it is configurable per backtest
# run, never silently assumed exact.
DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS = 45


@dataclass(frozen=True)
class AsOfDataset:
    """Everything AIDecisionEngine/RecommendationEngine need for one
    symbol, one historical evaluation date, plus the audit metadata a
    RecommendationSnapshot row needs to prove no future data leaked in.
    """

    context: AnalysisContext
    technical_input_as_of: Optional[datetime]
    fundamental_input_as_of: Optional[date]
    price_bar_source: Optional[str]
    price_bar_is_synthetic: Optional[bool]
    price_bars_df: Optional[pd.DataFrame] = None

    @property
    def has_any_input(self) -> bool:
        return self.context.technical_result is not None or self.context.fundamental_result is not None


def _end_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=timezone.utc)


def _start_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def load_as_of_dataset(
    session: Session,
    stock: Stock,
    as_of: date,
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    timeframe: Timeframe = Timeframe.ONE_DAY,
    period_type: PeriodType = PeriodType.ANNUAL,
) -> AsOfDataset:
    """Builds the AnalysisContext a decision made *on* `as_of` was
    allowed to see: price bars up to and including `as_of` (never
    later), and fundamentals whose fiscal period ended at least
    `fundamental_reporting_lag_days` before `as_of` (never a period
    that, from `as_of`'s point of view, wasn't public yet).

    Degrades exactly like the live REST routes do: too little price
    history (TechnicalAnalysisEngine's own >=35-bar rule) or no
    eligible fundamentals leaves that leg `None`, never raises.
    """
    as_of_end = _end_of_day_utc(as_of)

    df = load_price_bars(session, stock.id, timeframe, end=as_of_end)
    technical_result = None
    if not df.empty:
        try:
            technical_result = TechnicalAnalysisEngine().analyze(df)
        except ValueError:
            technical_result = None

    latest_bar = (
        session.query(PriceBar)
        .filter(
            PriceBar.stock_id == stock.id,
            PriceBar.timeframe == timeframe,
            PriceBar.timestamp <= as_of_end,
        )
        .order_by(PriceBar.timestamp.desc())
        .first()
    )
    technical_input_as_of = latest_bar.timestamp if latest_bar is not None else None
    latest_price = float(latest_bar.close) if latest_bar is not None else None
    price_bar_source = latest_bar.source if latest_bar is not None else None
    price_bar_is_synthetic = latest_bar.is_synthetic if latest_bar is not None else None

    reporting_cutoff = as_of - timedelta(days=fundamental_reporting_lag_days)
    snapshots = load_fundamental_snapshots(session, stock.id, period_type, limit=2, as_of=reporting_cutoff)
    fundamental_result = None
    fundamental_input_as_of = None
    if snapshots:
        latest, prior = snapshots[0], (snapshots[1] if len(snapshots) > 1 else None)
        fundamental_result = FundamentalAnalysisEngine().analyze(latest, prior_facts=prior, market_price=latest_price)
        fundamental_input_as_of = latest.fiscal_period_end

    context = AnalysisContext(
        symbol=stock.symbol,
        technical_result=technical_result,
        fundamental_result=fundamental_result,
        latest_price=latest_price,
    )

    return AsOfDataset(
        context=context,
        technical_input_as_of=technical_input_as_of,
        fundamental_input_as_of=fundamental_input_as_of,
        price_bar_source=price_bar_source,
        price_bar_is_synthetic=price_bar_is_synthetic,
        price_bars_df=df if not df.empty else None,
    )


def load_forward_price_path(
    session: Session,
    stock: Stock,
    from_date: date,
    horizon_days: int,
    timeframe: Timeframe = Timeframe.ONE_DAY,
) -> pd.DataFrame:
    """Price bars strictly *after* `from_date` through `from_date +
    horizon_days` -- deliberately forward-looking, for scoring a
    decision already made. Never call this to build an AnalysisContext;
    only `load_as_of_dataset()` is safe for that."""
    start = _start_of_day_utc(from_date) + timedelta(days=1)
    end = _end_of_day_utc(from_date + timedelta(days=horizon_days))
    return load_price_bars(session, stock.id, timeframe, start=start, end=end)


def bars_match_provenance(
    session: Session,
    stock_id: int,
    start: date,
    end: date,
    expect_synthetic: bool,
    timeframe: Timeframe = Timeframe.ONE_DAY,
) -> bool:
    """True if every PriceBar in [start, end] for this stock has
    `is_synthetic == expect_synthetic` -- the enforcement behind "never
    mix synthetic and live performance into one reported result." A
    symbol/date range with no bars at all trivially matches (nothing
    to contradict the expectation); BacktestingEngine's own "not enough
    data" handling is what skips it, not this check."""
    mismatch = (
        session.query(PriceBar.id)
        .filter(
            PriceBar.stock_id == stock_id,
            PriceBar.timeframe == timeframe,
            PriceBar.timestamp >= _start_of_day_utc(start),
            PriceBar.timestamp <= _end_of_day_utc(end),
            PriceBar.is_synthetic != expect_synthetic,
        )
        .first()
    )
    return mismatch is None
