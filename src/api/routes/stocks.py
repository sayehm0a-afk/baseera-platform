"""GET /api/v1/stocks/* -- consumer-facing REST API over the domain
layer, the live SAHMK/dev market and fundamental data providers, and
the existing M2.2/M2.3 analysis engines. Every route here is read-only,
with one disclosed exception: /decision-v2 additionally inserts a
best-effort `DecisionV2Snapshot` audit row on success (never updates or
deletes one) -- see that route's own docstring.

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

/decision, /decision-v2, and /analyst-report are three different views
over one computation, not three engines: each builds the same
AnalysisContext (via `_build_analysis_context`, itself a thin wrapper
over the shared `context_builder.build_analysis_context`) and calls
`AIDecisionEngine.decide()` through the single shared
`decision_pipeline.compute_investment_decision()` (see that module's
docstring) -- /decision-v2 then layers the 15 publication gates and
Arabic taxonomy on top (`DecisionEngineV2`), and /analyst-report layers
an LLM narrative on top (`AnalystEngine`), but neither recomputes the
underlying decision independently. /decision and /analyst-report are
kept as stable, unchanged-response-shape compatibility endpoints for
existing callers; /decision-v2 is the current canonical, gate-checked
decision surface.

Every route requires `require_active_subscription()` (Phase 13 P13.5
fix -- this entire file had *no* auth dependency at all before this,
meaning any anonymous caller could pull live quotes, technical/
fundamental analysis, and the full AI recommendation/decision/analyst-
report stack directly from the API, completely bypassing registration,
trial, and subscription. The frontend's RequireSession guard never
protected this -- it's client-side routing, not an API-layer control,
exactly the "never trust frontend entitlement checks" failure mode.
`require_active_subscription()` gives staff an unconditional bypass and
is satisfied by any TRIALING/ACTIVE/still-within-period CANCELED
subscription, so no real trial or paying customer loses access -- only
anonymous/expired callers are newly rejected).
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from src.analysis.analyst.analyst_engine_factory import get_analyst_engine
from src.analysis.analyst.output_formatter import OutputFormatter
from src.analysis.context_builder import build_analysis_context
from src.analysis.decision_pipeline import compute_investment_decision
from src.analysis.decision_v2.engine import DecisionEngineV2
from src.analysis.decision_v2.types import ANALYSIS_DISCLAIMER_AR, CONFIDENCE_DISCLAIMER_AR
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
    AnalystReportOut,
    DecisionFactorBreakdownOut,
    DecisionV2Out,
    FundamentalAnalysisOut,
    GateOutcomeOut,
    HistoricalBarOut,
    HistoryOut,
    InvestmentDecisionOut,
    QuoteOut,
    RecommendationOut,
    ScoreContributionOut,
    SignalOut,
    StockOut,
    StockSearchOut,
    StockSearchResultOut,
    SubScoresOut,
    TechnicalAnalysisOut,
)
from src.auth.rbac import require_active_subscription
from src.core.db.database import get_db
from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.arabic_text import normalize_arabic
from src.domain.models import DecisionV2Snapshot, FundamentalSnapshot, PeriodType, Stock, Timeframe, User
from src.domain.sector_labels import sector_label_ar
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkError
from src.market_data.validators.symbol_validator import InvalidSymbolError, validate_symbol_format
from src.market_intelligence.market_status import MarketSessionStatus, get_market_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


def _get_stock_or_404(session: Session, symbol: str) -> Stock:
    stock = session.query(Stock).filter(Stock.symbol == symbol).one_or_none()
    if stock is None:
        raise StockNotFoundError(f"No stock is registered for symbol '{symbol}'.")
    return stock


@router.get("/search", response_model=StockSearchOut)
def search_stocks(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_active_subscription()),
) -> StockSearchOut:
    """Search the registered symbol universe by Tadawul symbol, Arabic
    company name, or English company name -- a case-insensitive
    substring match against Stock.symbol/name_ar/name_en, the only
    real identifiers this platform stores (no fuzzy/phonetic matching,
    so a misspelled Arabic name may return no results rather than a
    guessed one). Registered *before* `/{symbol}` below so "search" is
    never swallowed as a literal symbol path parameter.

    A plain SQL `ILIKE` substring match alone would miss a real,
    common case in Arabic: "ارامكو" (no hamza), "أرامكو" (hamza on
    alef), and "أرامكو  السعودية" (extra internal spacing) are all the
    same company to a human reader but different byte sequences to
    the database. The cheap `ILIKE` path runs first and normally
    supplies every result; only when it comes back short of `limit`
    does a normalized-Arabic fallback scan the (small, ~250-symbol)
    active universe in Python via `normalize_arabic` -- see that
    module's docstring for exactly which letter/diacritic/whitespace
    variants it folds together.
    """
    query = q.strip()
    if not query:
        return StockSearchOut(query=q, results=[])

    like = f"%{query}%"
    stocks = (
        session.query(Stock)
        .filter(
            Stock.is_active.is_(True),
            (Stock.symbol.ilike(like) | Stock.name_ar.ilike(like) | Stock.name_en.ilike(like)),
        )
        .order_by(Stock.symbol)
        .limit(limit)
        .all()
    )

    if len(stocks) < limit:
        matched_symbols = {s.symbol for s in stocks}
        normalized_query = normalize_arabic(query)
        if normalized_query:
            candidates = session.query(Stock).filter(Stock.is_active.is_(True)).order_by(Stock.symbol).all()
            for candidate in candidates:
                if len(stocks) >= limit:
                    break
                if candidate.symbol in matched_symbols:
                    continue
                if candidate.name_ar and normalized_query in normalize_arabic(candidate.name_ar):
                    stocks.append(candidate)
                    matched_symbols.add(candidate.symbol)

    return StockSearchOut(
        query=q,
        results=[
            StockSearchResultOut(symbol=s.symbol, name_en=s.name_en, name_ar=s.name_ar, sector=s.sector)
            for s in stocks
        ],
    )


@router.get("/{symbol}", response_model=StockOut)
def get_stock(
    symbol: str,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_active_subscription()),
) -> Stock:
    return _get_stock_or_404(session, symbol)


@router.get("/{symbol}/quote", response_model=QuoteOut)
async def get_quote(
    symbol: str,
    provider: IMarketDataProvider = Depends(get_market_provider),
    _current_user: User = Depends(require_active_subscription()),
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
    _current_user: User = Depends(require_active_subscription()),
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
def get_technical_analysis(
    symbol: str,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_active_subscription()),
) -> TechnicalAnalysisOut:
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
    _current_user: User = Depends(require_active_subscription()),
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
    """Thin wrapper around the shared `build_analysis_context`
    (src/analysis/context_builder.py): resolves `symbol` to a `Stock`
    row (raising the API-layer 404 this route needs) and delegates the
    actual technical/fundamental/live-price assembly, so /recommendation,
    /decision, and /analyst-report keep the exact same call shape they
    already had. The assembly logic itself is no longer duplicated here
    -- src.market_intelligence's scanner reuses the same
    build_analysis_context for its market-wide pipeline.
    """
    stock = _get_stock_or_404(session, symbol)
    return await build_analysis_context(stock, period_type, session, market_provider)


@router.get("/{symbol}/recommendation", response_model=RecommendationOut)
async def get_recommendation(
    symbol: str,
    period_type: PeriodType = Query(PeriodType.ANNUAL),
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
    _current_user: User = Depends(require_active_subscription()),
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
    _current_user: User = Depends(require_active_subscription()),
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

    decision = compute_investment_decision(context)

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
        entry_quality=decision.entry_quality.value,
        entry_quality_notes=decision.entry_quality_notes,
        risk_reward_ratio=decision.risk_reward_ratio,
        stop_loss_basis=decision.stop_loss_basis,
        target_price_basis=decision.target_price_basis,
        confidence_calibration_notes=decision.confidence_calibration_notes,
    )


def _parse_quote_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _sub_scores_dict(sub_scores) -> dict:
    """The one place a DecisionResult's `sub_scores` gets unpacked into
    a plain dict -- reused for both the DecisionV2Snapshot audit row's
    JSON column and (via `SubScoresOut(**...)`) the DecisionV2Out
    response, so the two representations can never silently drift
    apart from each other."""
    return {
        "trend_score": sub_scores.trend_score,
        "momentum_score": sub_scores.momentum_score,
        "volume_score": sub_scores.volume_score,
        "liquidity_score": sub_scores.liquidity_score,
        "volatility_score": sub_scores.volatility_score,
        "risk_reward_score": sub_scores.risk_reward_score,
        "market_context_score": sub_scores.market_context_score,
        "data_quality_score": sub_scores.data_quality_score,
    }


def _gates_as_dicts(gates) -> list:
    """Same reasoning as `_sub_scores_dict`, for DecisionResult.gates --
    reused for both the audit row's JSON column and (via
    `GateOutcomeOut(**...)`) the response."""
    return [{"name": g.name, "passed": g.passed, "detail": g.detail, "blocking": g.blocking} for g in gates]


@router.get("/{symbol}/decision-v2", response_model=DecisionV2Out)
async def get_decision_v2(
    symbol: str,
    period_type: PeriodType = Query(PeriodType.ANNUAL),
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
    current_user: User = Depends(require_active_subscription()),
) -> DecisionV2Out:
    """Decision Engine V2 (Phase 1): the Arabic-labeled, gate-checked
    action Basirah recommends for one symbol -- STRONG_BUY_CANDIDATE
    through INSUFFICIENT_DATA, never a plain BUY/SELL score band --
    plus a real entry zone, up to three targets, an expected holding
    period, eight documented sub-scores, and the full list of the 15
    publication gates that decided the outcome. See
    src/analysis/decision_v2/ for the engine itself; this route only
    assembles its inputs (the same AnalysisContext /recommendation,
    /decision, and /analyst-report already build) and maps its output.

    Never claims a STRONG_BUY_CANDIDATE/BUY_CANDIDATE unless every
    mandatory gate passes -- a poor entry, stale data, thin liquidity,
    or a price that has already run past a sane entry zone all
    downgrade the decision instead of encouraging a bad or synthetic
    purchase. `confidence_score` measures evidence strength, never a
    probability of profit (`confidence_disclaimer_ar`), and every
    actionable decision carries `analysis_disclaimer_ar` verbatim --
    Basirah must never claim a guaranteed outcome.

    Best-effort audit: on success, a `DecisionV2Snapshot` row is
    inserted (never updated/deleted) so this decision can be reviewed
    later -- see that model's docstring for why persistence is
    insert-only. A persistence failure never fails this GET; it is
    logged and rolled back so the read-only response is unaffected.
    """
    context = await _build_analysis_context(symbol, period_type, session, market_provider)

    if context.technical_result is None and context.fundamental_result is None:
        raise InsufficientDataError(
            f"Not enough ingested history or fundamentals for '{symbol}' to generate a decision."
        )

    investment_decision = compute_investment_decision(context)

    stock = _get_stock_or_404(session, symbol)
    quote_info = context.extra.get("quote", {})
    market_info = get_market_status()

    result = DecisionEngineV2().decide(
        context,
        investment_decision,
        company_name_ar=stock.name_ar,
        company_name_en=stock.name_en,
        sector=stock.sector,
        sector_ar=sector_label_ar(stock.sector),
        is_synthetic=quote_info.get("is_synthetic"),
        data_source=quote_info.get("source") or "unknown",
        quote_timestamp=_parse_quote_timestamp(quote_info.get("timestamp")),
        market_status=market_info.status.value,
        market_is_open=market_info.status == MarketSessionStatus.OPEN,
    )

    try:
        session.add(
            DecisionV2Snapshot(
                stock_id=stock.id,
                symbol=result.symbol,
                company_name_ar=result.company_name_ar,
                company_name_en=result.company_name_en,
                sector_ar=result.sector_ar,
                decision=result.decision.value,
                decision_label_ar=result.decision_label_ar,
                confidence_score=result.confidence_score,
                opportunity_quality_score=result.opportunity_quality_score,
                risk_score=result.risk_score,
                data_quality_score=result.data_quality_score,
                data_freshness_status=result.data_freshness_status.value,
                current_price=result.current_price,
                entry_zone_low=result.entry_zone_low,
                entry_zone_high=result.entry_zone_high,
                stop_loss=result.stop_loss,
                target_1=result.target_1,
                target_2=result.target_2,
                target_3=result.target_3,
                expected_return_target_1=result.expected_return_target_1,
                expected_return_target_2=result.expected_return_target_2,
                downside_to_stop=result.downside_to_stop,
                risk_reward_target_1=result.risk_reward_target_1,
                risk_reward_target_2=result.risk_reward_target_2,
                expected_holding_period_min_days=result.expected_holding_period_min_days,
                expected_holding_period_max_days=result.expected_holding_period_max_days,
                expected_holding_period_label_ar=result.expected_holding_period_label_ar,
                horizon_type=result.horizon_type,
                market_status=result.market_status,
                decision_timestamp=result.decision_timestamp,
                invalidation_conditions=result.invalidation_conditions,
                positive_reasons=result.positive_reasons,
                negative_reasons=result.negative_reasons,
                warnings=result.warnings,
                recommendation_basis=result.recommendation_basis,
                sub_scores=_sub_scores_dict(result.sub_scores),
                gates=_gates_as_dicts(result.gates),
                analysis_version=result.analysis_version,
                data_source=result.data_source,
                is_synthetic=quote_info.get("is_synthetic"),
                scan_run_id=result.scan_run_id,
                requested_by_user_id=current_user.id,
            )
        )
        session.commit()
    except Exception:  # noqa: BLE001 -- audit persistence must never break a read-only GET
        logger.exception("Failed to persist DecisionV2Snapshot for '%s' -- response is unaffected.", symbol)
        session.rollback()

    return DecisionV2Out(
        symbol=result.symbol,
        company_name_ar=result.company_name_ar,
        company_name_en=result.company_name_en,
        sector_ar=result.sector_ar,
        decision=result.decision.value,
        decision_label_ar=result.decision_label_ar,
        confidence_score=result.confidence_score,
        confidence_disclaimer_ar=CONFIDENCE_DISCLAIMER_AR,
        opportunity_quality_score=result.opportunity_quality_score,
        risk_score=result.risk_score,
        data_quality_score=result.data_quality_score,
        data_freshness_status=result.data_freshness_status.value,
        current_price=result.current_price,
        entry_zone_low=result.entry_zone_low,
        entry_zone_high=result.entry_zone_high,
        stop_loss=result.stop_loss,
        target_1=result.target_1,
        target_2=result.target_2,
        target_3=result.target_3,
        expected_return_target_1=result.expected_return_target_1,
        expected_return_target_2=result.expected_return_target_2,
        downside_to_stop=result.downside_to_stop,
        risk_reward_target_1=result.risk_reward_target_1,
        risk_reward_target_2=result.risk_reward_target_2,
        expected_holding_period_min_days=result.expected_holding_period_min_days,
        expected_holding_period_max_days=result.expected_holding_period_max_days,
        expected_holding_period_label_ar=result.expected_holding_period_label_ar,
        horizon_type=result.horizon_type,
        market_status=result.market_status,
        decision_timestamp=result.decision_timestamp,
        invalidation_conditions=result.invalidation_conditions,
        positive_reasons=result.positive_reasons,
        negative_reasons=result.negative_reasons,
        warnings=result.warnings,
        recommendation_basis=result.recommendation_basis,
        analysis_disclaimer_ar=ANALYSIS_DISCLAIMER_AR,
        analysis_version=result.analysis_version,
        data_source=result.data_source,
        scan_run_id=result.scan_run_id,
        sub_scores=SubScoresOut(**_sub_scores_dict(result.sub_scores)),
        gates=[GateOutcomeOut(**g) for g in _gates_as_dicts(result.gates)],
        is_real_data=result.is_real_data,
        quote_timestamp=result.quote_timestamp,
        technical_confidence=result.technical_confidence,
        momentum_confidence=result.momentum_confidence,
        liquidity_confidence=result.liquidity_confidence,
        market_context_confidence=result.market_context_confidence,
        data_quality_confidence=result.data_quality_confidence,
        trade_type=result.trade_type.value if result.trade_type else None,
        trade_type_label_ar=result.trade_type_label_ar,
        time_horizon_rationale_ar=result.time_horizon_rationale_ar,
        best_entry_price=result.best_entry_price,
        accumulation_zone_low=result.accumulation_zone_low,
        accumulation_zone_high=result.accumulation_zone_high,
        entry_quality=result.entry_quality,
        entry_quality_label_ar=result.entry_quality_label_ar,
        entry_status=result.entry_status.value,
        entry_status_label_ar=result.entry_status_label_ar,
        invalidation_price=result.invalidation_price,
        risk_level=result.risk_level,
        risk_level_label_ar=result.risk_level_label_ar,
        estimated_days_target_1=result.estimated_days_target_1,
        estimated_days_target_2=result.estimated_days_target_2,
        estimated_days_target_3=result.estimated_days_target_3,
        nearest_support=result.nearest_support,
        major_support=result.major_support,
        nearest_resistance=result.nearest_resistance,
        major_resistance=result.major_resistance,
        breakout_level=result.breakout_level,
        breakdown_level=result.breakdown_level,
        support_resistance_evidence_ar=result.support_resistance_evidence_ar,
        current_volume=result.current_volume,
        average_volume=result.average_volume,
        relative_volume=result.relative_volume,
        liquidity_quality_ar=result.liquidity_quality_ar,
        accumulation_score=result.accumulation_score,
        accumulation_assessment_ar=result.accumulation_assessment_ar,
        volume_confirms_decision=result.volume_confirms_decision,
        abnormal_volume=result.abnormal_volume,
        technical_evidence=result.technical_evidence,
        trend_direction_ar=result.trend_direction_ar,
        trend_strength_label_ar=result.trend_strength_label_ar,
        decision_summary_ar=result.decision_summary_ar,
        why_now_ar=result.why_now_ar,
        why_not_stronger_ar=result.why_not_stronger_ar,
        entry_confirmation_conditions_ar=result.entry_confirmation_conditions_ar,
        watch_next_session_ar=result.watch_next_session_ar,
    )


@router.get("/{symbol}/analyst-report")
async def get_analyst_report(
    symbol: str,
    period_type: PeriodType = Query(PeriodType.ANNUAL),
    format: str = Query("json", pattern="^(json|markdown|text)$"),
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
    current_user: User = Depends(require_active_subscription()),
):
    """The Autonomous AI Analyst Framework's report for one symbol:
    everything /decision already produces, narrated into a
    twelve-section human-quality explanation (investment summary,
    technical/fundamental/risk reasoning, bullish/bearish factors,
    confidence/target price/stop loss/time horizon explanations,
    alternative scenarios, and a final rationale) -- see
    src/analysis/analyst/ for the orchestration logic. This route
    computes no score, target, or confidence value itself; every
    number comes from the same AIDecisionEngine /decision already
    calls. The same graceful-degradation and 422 rules as
    /recommendation and /decision apply, since AnalystEngine runs the
    same two engines first.

    The technical/fundamental/risk narrative paragraphs are rephrased
    by a real LLM (src/analysis/analyst/openai_llm_adapter.py) when
    OPENAI_API_KEY is configured, grounded in and verified against the
    same deterministic baseline text every environment without a key
    already returns -- see get_analyst_engine()'s module docstring.
    Every number in the report always comes from AIDecisionEngine,
    never from the LLM.

    `format=markdown` and `format=text` return the same report
    rendered as Markdown or plain text (e.g. for a rendered report
    view or a log/email) instead of JSON.
    """
    context = await _build_analysis_context(symbol, period_type, session, market_provider)

    if context.technical_result is None and context.fundamental_result is None:
        raise InsufficientDataError(
            f"Not enough ingested history or fundamentals for '{symbol}' to generate an analyst report."
        )

    report = await get_analyst_engine(session).analyze(context, requesting_user_id=current_user.id)

    if format == "markdown":
        return PlainTextResponse(OutputFormatter.to_markdown(report), media_type="text/markdown")
    if format == "text":
        return PlainTextResponse(OutputFormatter.to_text(report), media_type="text/plain")

    decision = report.decision
    explanation = report.explanation
    return AnalystReportOut(
        symbol=report.symbol,
        recommendation=decision.recommendation.value,
        confidence=decision.confidence,
        final_score=decision.final_score,
        target_price=decision.target_price,
        stop_loss=decision.stop_loss,
        time_horizon=decision.time_horizon.value,
        expected_return_pct=decision.expected_return_pct,
        risk_level=decision.risk_level.value,
        position_size=decision.position_size.value,
        investment_summary=explanation.investment_summary,
        technical_reasoning=explanation.technical_reasoning,
        fundamental_reasoning=explanation.fundamental_reasoning,
        risk_explanation=explanation.risk_explanation,
        bullish_factors=explanation.bullish_factors,
        bearish_factors=explanation.bearish_factors,
        confidence_explanation=explanation.confidence_explanation,
        target_price_explanation=explanation.target_price_explanation,
        stop_loss_explanation=explanation.stop_loss_explanation,
        time_horizon_explanation=explanation.time_horizon_explanation,
        alternative_scenarios=explanation.alternative_scenarios,
        final_recommendation_rationale=explanation.final_recommendation_rationale,
        generated_at=report.generated_at,
        engine_version=report.engine_version,
        entry_quality=decision.entry_quality.value,
        entry_quality_notes=decision.entry_quality_notes,
        risk_reward_ratio=decision.risk_reward_ratio,
        stop_loss_basis=decision.stop_loss_basis,
        target_price_basis=decision.target_price_basis,
        confidence_calibration_notes=decision.confidence_calibration_notes,
    )
