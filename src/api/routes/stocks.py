"""GET /api/v1/stocks/* -- consumer-facing REST API over the domain
layer, the live SAHMK/dev market and fundamental data providers, and
the existing M2.2/M2.3 analysis engines. Every route here is read-only.

/quote is a live pass-through (no DB row required) -- it never persists
anything, so it doesn't need the symbol to already be a registered
Stock; the provider layer's own symbol-format validation is enough.
/history, /technical, and /fundamentals all read from the database, so
they do require an existing Stock row -- there is nothing to read
otherwise.

Known, disclosed gap: PriceBar (unlike FundamentalSnapshot) has no
source/is_synthetic columns, so /history cannot currently tell a caller
whether a given historical bar came from real SAHMK data or the
synthetic dev provider once it's been ingested into the database --
only /quote and /fundamentals, which read directly from a provider or
from FundamentalSnapshot (which does have those columns), can. Adding
that column is a schema migration, tracked as follow-up work, not done
here.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.analysis.decision.ai_decision_engine import AIDecisionEngine
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.fundamental_loader import load_fundamental_snapshots
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.types import AnalysisContext
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.api.dependencies import get_market_provider
from src.api.exceptions import (
    InsufficientDataError,
    InvalidSymbolFormatError,
    ProviderUnavailableError,
    StockNotFoundError,
)
from src.api.schemas.stocks import (
    DecisionFactorBreakdownOut,
    FundamentalAnalysisOut,
    HistoricalBarOut,
    HistoryOut,
    InvestmentDecisionOut,
    QuoteOut,
    RecommendationOut,
    ScoreContributionOut,
    SignalOut,
    StockOut,
    TechnicalAnalysisOut,
)
from src.core.db.database import get_db
from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import FundamentalSnapshot, PeriodType, Stock, Timeframe
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkError
from src.market_data.validators.symbol_validator import InvalidSymbolError, validate_symbol_format

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


def _get_stock_or_404(session: Session, symbol: str) -> Stock:
    stock = session.query(Stock).filter(Stock.symbol == symbol).one_or_none()
    if stock is None:
        raise StockNotFoundError(f"No stock is registered for symbol '{symbol}'.")
    return stock


@router.get("/{symbol}", response_model=StockOut)
def get_stock(symbol: str, session: Session = Depends(get_db)) -> Stock:
    return _get_stock_or_404(session, symbol)


@router.get("/{symbol}/quote", response_model=QuoteOut)
async def get_quote(
    symbol: str,
    provider: IMarketDataProvider = Depends(get_market_provider),
) -> QuoteOut:
    # Validated here, at the API boundary, rather than relying on the
    # provider to reject a malformed symbol -- SahmkClient does, but
    # IMarketDataProvider's interface doesn't require it, and
    # DevMarketDataProvider doesn't (it happily synthesizes data for
    # any input string). Consumer-facing behavior must not depend on
    # which provider happens to be selected.
    try:
        validate_symbol_format(symbol)
    except InvalidSymbolError as exc:
        raise InvalidSymbolFormatError(str(exc)) from exc

    try:
        data = await provider.get_stock_data(symbol)
    except InvalidSymbolError as exc:
        raise InvalidSymbolFormatError(str(exc)) from exc
    except (SahmkError, CircuitBreakerOpenError) as exc:
        raise ProviderUnavailableError(f"Could not fetch a live quote for '{symbol}': {exc}") from exc
    return QuoteOut(**data)


@router.get("/{symbol}/history", response_model=HistoryOut)
def get_history(
    symbol: str,
    start: Optional[datetime] = Query(
        None, description="Inclusive start (ISO-8601); omit for all ingested history"
    ),
    end: Optional[datetime] = Query(
        None, description="Inclusive end (ISO-8601); omit for up to the latest ingested bar"
    ),
    session: Session = Depends(get_db),
) -> HistoryOut:
    stock = _get_stock_or_404(session, symbol)
    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY, start=start, end=end)
    bars = [
        HistoricalBarOut(
            timestamp=timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for timestamp, row in df.iterrows()
    ]
    return HistoryOut(symbol=symbol, timeframe=Timeframe.ONE_DAY.value, bars=bars)


@router.get("/{symbol}/technical", response_model=TechnicalAnalysisOut)
def get_technical_analysis(symbol: str, session: Session = Depends(get_db)) -> TechnicalAnalysisOut:
    stock = _get_stock_or_404(session, symbol)
    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)
    try:
        result = TechnicalAnalysisEngine().analyze(df)
    except ValueError as exc:
        raise InsufficientDataError(
            f"Not enough ingested history for '{symbol}' to run technical analysis: {exc}"
        ) from exc
    return TechnicalAnalysisOut(
        symbol=symbol,
        timeframe=Timeframe.ONE_DAY.value,
        bars_used=len(df),
        as_of=df.index[-1].to_pydatetime(),
        indicators=result.latest_snapshot(),
    )


@router.get("/{symbol}/fundamentals", response_model=FundamentalAnalysisOut)
async def get_fundamental_analysis(
    symbol: str,
    period_type: PeriodType = Query(PeriodType.ANNUAL),
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
) -> FundamentalAnalysisOut:
    stock = _get_stock_or_404(session, symbol)
    snapshots = load_fundamental_snapshots(session, stock.id, period_type, limit=2)
    if not snapshots:
        raise InsufficientDataError(
            f"No {period_type.value} fundamentals have been ingested yet for '{symbol}'."
        )
    latest, prior = snapshots[0], (snapshots[1] if len(snapshots) > 1 else None)

    market_price: Optional[float] = None
    try:
        quote = await market_provider.get_stock_data(symbol)
        market_price = quote.get("close")
    except (SahmkError, CircuitBreakerOpenError) as exc:
        # Valuation ratios (P/E, P/B, market cap) are simply omitted
        # (None) when no live price is available -- the rest of the
        # ratio set (profitability/liquidity/leverage/growth) needs no
        # market price at all, so a provider outage must not fail this
        # whole endpoint.
        logger.info(
            "Could not fetch a live price for '%s' fundamentals valuation ratios: %s", symbol, exc
        )

    result = FundamentalAnalysisEngine().analyze(latest, prior_facts=prior, market_price=market_price)

    # source/is_synthetic live on the stored FundamentalSnapshot row, not
    # on FundamentalFacts (the pure-computation shape ratios are computed
    # from) -- read them back from the row load_fundamental_snapshots
    # already queried, by the same identity it queried on.
    snapshot_row = (
        session.query(FundamentalSnapshot)
        .filter_by(
            stock_id=stock.id,
            period_type=period_type,
            fiscal_period_end=latest.fiscal_period_end,
        )
        .one()
    )

    return FundamentalAnalysisOut(
        symbol=symbol,
        period_type=period_type.value,
        fiscal_period_end=latest.fiscal_period_end.isoformat(),
        ratios=result.latest_snapshot(),
        source=snapshot_row.source,
        is_synthetic=snapshot_row.is_synthetic,
    )


async def _build_analysis_context(
    symbol: str,
    period_type: PeriodType,
    session: Session,
    market_provider: IMarketDataProvider,
) -> AnalysisContext:
    """Assembles the technical/fundamental/live-price inputs shared by
    /recommendation and /decision -- both routes need the exact same
    "run the two existing analysis engines against this symbol's
    ingested data" work, so it lives once here rather than being
    duplicated in each route. Each leg degrades independently and
    gracefully: insufficient price history, no ingested fundamentals,
    or a provider outage on the live quote only omits that piece
    (`None`), never raises -- the caller decides whether the resulting
    context has enough to proceed.
    """
    stock = _get_stock_or_404(session, symbol)

    technical_result = None
    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)
    try:
        technical_result = TechnicalAnalysisEngine().analyze(df)
    except ValueError as exc:
        logger.info("Technical leg unavailable for '%s': %s", symbol, exc)

    market_price: Optional[float] = None
    try:
        quote = await market_provider.get_stock_data(symbol)
        market_price = quote.get("close")
    except (SahmkError, CircuitBreakerOpenError) as exc:
        logger.info("Could not fetch a live price for '%s': %s", symbol, exc)

    fundamental_result = None
    snapshots = load_fundamental_snapshots(session, stock.id, period_type, limit=2)
    if snapshots:
        latest, prior = snapshots[0], (snapshots[1] if len(snapshots) > 1 else None)
        fundamental_result = FundamentalAnalysisEngine().analyze(
            latest, prior_facts=prior, market_price=market_price
        )

    return AnalysisContext(
        symbol=symbol,
        technical_result=technical_result,
        fundamental_result=fundamental_result,
        latest_price=market_price,
    )


@router.get("/{symbol}/recommendation", response_model=RecommendationOut)
async def get_recommendation(
    symbol: str,
    period_type: PeriodType = Query(PeriodType.ANNUAL),
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
) -> RecommendationOut:
    """BUY/HOLD/SELL with a confidence score, produced by
    RecommendationEngine combining the existing TechnicalAnalysisEngine
    and FundamentalAnalysisEngine -- see src/analysis/recommendation/
    for the orchestration logic. Each leg degrades independently and
    gracefully (missing history, no ingested fundamentals, or a
    provider outage on the valuation price only lowers that leg's
    weight/confidence, exactly like /technical and /fundamentals
    already do on their own); only a symbol with *neither* leg
    available is a 422, since a recommendation with zero inputs would
    not be an honest response.
    """
    context = await _build_analysis_context(symbol, period_type, session, market_provider)

    if context.technical_result is None and context.fundamental_result is None:
        raise InsufficientDataError(
            f"Not enough ingested history or fundamentals for '{symbol}' to generate a recommendation."
        )

    result = RecommendationEngine().generate(context)

    return RecommendationOut(
        symbol=result.symbol,
        recommendation=result.recommendation.value,
        confidence=result.confidence,
        explanation=result.explanation,
        technical_score=result.technical_score,
        fundamental_score=result.fundamental_score,
        final_score=result.final_score,
        contributions=[
            ScoreContributionOut(
                source=c.source, score=c.score, weight=c.weight, confidence=c.confidence, notes=c.notes
            )
            for c in result.contributions
        ],
        signals=[
            SignalOut(name=s.name, description=s.description, direction=s.direction.value, source=s.source, impact=s.impact)
            for s in result.signals
        ],
        generated_at=result.generated_at,
    )


@router.get("/{symbol}/decision", response_model=InvestmentDecisionOut)
async def get_investment_decision(
    symbol: str,
    period_type: PeriodType = Query(PeriodType.ANNUAL),
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
) -> InvestmentDecisionOut:
    """The AI Decision Intelligence Layer's final output for one
    symbol: everything /recommendation already produces, plus a target
    price, stop loss, time horizon, expected return, risk level,
    position-size recommendation, plain-language reasons, and a
    category-level explainable breakdown -- see
    src/analysis/decision/ai_decision_engine.py. Built entirely on top
    of RecommendationEngine (itself built on TechnicalAnalysisEngine/
    FundamentalAnalysisEngine); the same graceful-degradation and 422
    rules as /recommendation apply, since this endpoint runs the same
    two engines first.
    """
    context = await _build_analysis_context(symbol, period_type, session, market_provider)

    if context.technical_result is None and context.fundamental_result is None:
        raise InsufficientDataError(
            f"Not enough ingested history or fundamentals for '{symbol}' to generate an investment decision."
        )

    decision = AIDecisionEngine().decide(context)

    return InvestmentDecisionOut(
        symbol=decision.symbol,
        recommendation=decision.recommendation.value,
        confidence=decision.confidence,
        final_score=decision.final_score,
        target_price=decision.target_price,
        stop_loss=decision.stop_loss,
        time_horizon=decision.time_horizon.value,
        expected_return_pct=decision.expected_return_pct,
        risk_level=decision.risk_level.value,
        position_size=decision.position_size.value,
        reasons=decision.reasons,
        breakdown=[
            DecisionFactorBreakdownOut(
                category=b.category, points=b.points, weight=b.weight,
                confidence=b.confidence, available=b.available, notes=b.notes,
            )
            for b in decision.breakdown
        ],
        signals=[
            SignalOut(name=s.name, description=s.description, direction=s.direction.value, source=s.source, impact=s.impact)
            for s in decision.signals
        ],
        generated_at=decision.generated_at,
    )
