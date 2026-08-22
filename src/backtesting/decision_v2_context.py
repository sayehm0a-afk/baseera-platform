"""As-of-safe context reconstruction for the DecisionEngineV2 historical
validation harness (Phase 3 historical validation gate, authorized by
the "BASIRAH -- PHASE 3 DECISIONENGINEV2 HISTORICAL VALIDATION HARNESS"
mandate). Builds every input `DecisionEngineV2.decide()` consumes for
one (stock, evaluation date) point, using ONLY data that would
genuinely have been available at that historical instant -- reusing
`src.backtesting.data_access.load_as_of_dataset()` for the technical/
fundamental legs it already gets right, and adding the Phase 3-specific
legs (sector-relative strength, breakout confirmation) plus the
remaining DecisionEngineV2.decide() keyword arguments on top.

Every historical feature that cannot be safely reconstructed is
listed explicitly in `DecisionV2AsOfContext.unavailable_features` and
never silently substituted with a live/current value:

  - news_sentiment: `NewsIntelligenceService` has no as-of query path
    (its LLM-analyzed `NewsEvent` rows carry no reliable "this was
    known as of date X" cutoff independent of ingestion time) -- this
    leg is always omitted from `extra` for both engines equally, so it
    never advantages either arm of the comparison.
  - market_breadth: always `None`. Reconstructing it correctly would
    require evaluating the ENTIRE scanned universe for the same date
    first and aggregating buy/sell counts across all of them before
    finalizing any single symbol's decision -- a real two-pass design
    the harness's runner (decision_v2_replay.py) does not implement in
    this first version. `None` here means `market_risk.classify_
    market_risk()` degrades to `INSUFFICIENT_DATA` for every
    evaluation, identically for Baseline and Phase 3 -- this cannot
    bias the A/B comparison, it can only reduce the market-risk-aware
    confidence caps both arms would otherwise apply, equally.
  - live bid/ask spread: no historical tick-level quote data exists in
    this platform (only daily bars) -- `extra["quote"]["bid"/"ask"]`
    are always `None`.
  - `quote_timestamp` stands in for a live tick timestamp using the
    as-of date's own latest daily bar timestamp -- the only real
    timestamp that exists for a historical date in a daily-bar-only
    platform.
  - `sector`/`sector_ar` are read from the CURRENT `Stock.sector`
    value, not a historical snapshot -- this platform does not persist
    sector-classification history, so a stock that was reclassified
    since the evaluation date would (incorrectly) show today's sector.
    Disclosed, not hidden; affects both arms identically.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from src.analysis.decision_v2.breakout_confirmation import BreakoutStatus, compute_breakout_confirmation
from src.analysis.decision_v2.evidence import derive_support_resistance
from src.analysis.decision_v2.sector_strength import compute_sector_strength
from src.analysis.recommendation.types import AnalysisContext
from src.backtesting.data_access import (
    DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    AsOfDataset,
    load_as_of_dataset,
)
from src.domain.models import Stock
from src.domain.sector_labels import sector_label_ar
from src.market_intelligence.trading_calendar import is_market_open

UNAVAILABLE_FEATURES: Tuple[str, ...] = ("news_sentiment", "market_breadth", "live_bid_ask")


def _end_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DecisionV2AsOfContext:
    """Everything `DecisionEngineV2.decide()` needs for one (stock,
    as_of date) point, reconstructed using only as-of-safe data. See
    this module's docstring for exactly which inputs are honestly
    unavailable rather than silently substituted."""

    context: AnalysisContext
    company_name_ar: Optional[str]
    company_name_en: str
    sector: Optional[str]
    sector_ar: Optional[str]
    is_synthetic: Optional[bool]
    data_source: str
    quote_timestamp: Optional[datetime]
    market_status: str
    market_is_open: bool
    market_breadth: None = None
    unavailable_features: Tuple[str, ...] = field(default_factory=lambda: UNAVAILABLE_FEATURES)

    @property
    def has_any_input(self) -> bool:
        return self.context.technical_result is not None or self.context.fundamental_result is not None


def build_decision_v2_as_of_context(
    session: Session,
    stock: Stock,
    as_of: date,
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
) -> DecisionV2AsOfContext:
    """The single entry point both the Baseline-V2 and Phase-3-V2
    strategies call with an identical `as_of` date -- guaranteeing item
    8's "same symbols/dates/timestamps/price history/fundamental
    history/market context" requirement structurally, not by
    convention: there is only one code path that builds this input,
    and both engine variants are handed the exact same object."""
    base: AsOfDataset = load_as_of_dataset(session, stock, as_of, fundamental_reporting_lag_days)
    as_of_end = _end_of_day_utc(as_of)

    extra: Dict[str, Any] = {}

    if base.price_bars_df is not None:
        extra["bars_used"] = len(base.price_bars_df)

        try:
            sector_result = compute_sector_strength(session, stock, base.price_bars_df, as_of=as_of_end)
        except Exception:  # noqa: BLE001 -- an optional leg must never break the whole context
            sector_result = None
        if sector_result is not None and sector_result.sector_strength_used:
            extra["sector_rotation"] = {
                "sector_relative_strength": sector_result.stock_vs_sector_relative_strength,
                "sector_strength_score": sector_result.sector_strength_score,
                "sector_data_timestamp": sector_result.sector_data_timestamp,
                "sector_strength_used": sector_result.sector_strength_used,
            }

        if base.context.technical_result is not None:
            sr_evidence = derive_support_resistance(
                base.context.latest_price, base.context.technical_result.support_resistance
            )
            volume_sma = base.context.technical_result.indicators.get("volume_sma_20")
            volume_series = volume_sma.value if volume_sma is not None else None
            try:
                breakout_result = compute_breakout_confirmation(
                    base.price_bars_df, sr_evidence.breakout_level, volume_series
                )
            except Exception:  # noqa: BLE001 -- an optional leg must never break the whole context
                breakout_result = None
            if breakout_result is not None and breakout_result.status is not BreakoutStatus.NOT_APPLICABLE:
                extra["breakout_confirmation"] = {
                    "status": breakout_result.status.value,
                    "hold_days": breakout_result.hold_days,
                    "volume_confirmed": breakout_result.volume_confirmed,
                    "follow_through_pct": breakout_result.follow_through_pct,
                    "explanation_ar": breakout_result.explanation_ar,
                }

    if base.context.latest_price is not None:
        extra["quote"] = {
            "price": base.context.latest_price,
            "change": None,
            "change_percent": None,
            "volume": None,
            "timestamp": base.technical_input_as_of.isoformat() if base.technical_input_as_of else None,
            "source": base.price_bar_source,
            "is_synthetic": base.price_bar_is_synthetic,
            "bid": None,
            "ask": None,
        }

    context = AnalysisContext(
        symbol=base.context.symbol,
        technical_result=base.context.technical_result,
        fundamental_result=base.context.fundamental_result,
        latest_price=base.context.latest_price,
        extra=extra,
    )

    market_is_open_flag = is_market_open(as_of_end)

    return DecisionV2AsOfContext(
        context=context,
        company_name_ar=stock.name_ar,
        company_name_en=stock.name_en or stock.symbol,
        sector=stock.sector,
        sector_ar=sector_label_ar(stock.sector),
        is_synthetic=base.price_bar_is_synthetic,
        data_source=base.price_bar_source or "unknown",
        quote_timestamp=base.technical_input_as_of,
        market_status="OPEN" if market_is_open_flag else "CLOSED",
        market_is_open=market_is_open_flag,
    )
