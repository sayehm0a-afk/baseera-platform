"""GET /api/v1/analysis/{symbol}/{technical,fundamental,composite,councils/technical}

Every handler below does exactly three things: load already-persisted
data via the existing loaders (`load_price_bars`, `load_fundamental_
snapshots`), call the existing engine's own `.analyze()` method
unchanged, and wrap the existing result in the common response
envelope. No indicator, ratio, factor, or expert computation is
duplicated or reimplemented here -- every number in every response was
computed by code that existed before this milestone.

Symbol resolution and 404-on-unknown-symbol are handled once, by the
shared `get_stock_or_404` dependency (src/api/dependencies.py), not
repeated per route.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.analysis.composite.composite_intelligence_engine import CompositeIntelligenceEngine
from src.analysis.composite.types import build_envelope, classify_freshness
from src.analysis.experts.council_engine import CouncilEngine
from src.analysis.experts.types import Council
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.fundamental_loader import load_fundamental_snapshots
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.api.dependencies import get_current_principal, get_db, get_stock_or_404
from src.api.exceptions import InsufficientDataError
from src.api.middleware.request_id import get_request_id
from src.api.schemas.analysis import (
    CompositeAnalysisResponse,
    CompositeFactorSchema,
    CouncilAnalysisResponse,
    EvidenceItemSchema,
    ExpertResultSchema,
    FundamentalAnalysisResponse,
    IndicatorSummary,
    RatioSummary,
    TechnicalAnalysisResponse,
)
from src.api.schemas.envelope import Envelope, Meta
from src.domain.models import PeriodType, Stock, Timeframe

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_FUNDAMENTAL_SNAPSHOT_LIMIT = 2  # latest + one prior period, matching FundamentalAnalysisEngine.analyze()'s own shape


def _now_meta(request: Request, as_of_reference: datetime) -> Meta:
    """Builds Meta with as_of = wall-clock computation time and
    freshness classified against `as_of_reference` (the underlying
    data's own recency) -- the same as_of/freshness distinction already
    established for EngineResultEnvelope (see envelope.py's module
    docstring). Both call sites (technical/fundamental) always have a
    real reference by the time this is called -- each raises
    InsufficientDataError earlier if their underlying data is empty --
    so this deliberately does not handle a None reference as a third
    case; there is no real caller for it.
    """
    now = datetime.now(timezone.utc)
    reference = as_of_reference
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    freshness = classify_freshness(as_of=reference, now=now).value
    return Meta(as_of=now, freshness=freshness, request_id=get_request_id(request))


def _load_technical_result(db: Session, stock: Stock):
    """Returns (TechnicalAnalysisResult, last_bar_timestamp, latest_close)
    from a single price-bar query -- callers needing the latest close
    (e.g. for fundamental valuation ratios) must not issue a second,
    redundant query for data already loaded here."""
    price_df = load_price_bars(db, stock.id, Timeframe.ONE_DAY)
    if price_df.empty:
        raise InsufficientDataError(f"No price history available for '{stock.symbol}'")
    last_bar_at = price_df.index[-1]
    latest_close = float(price_df["close"].iloc[-1])
    result = TechnicalAnalysisEngine().analyze(price_df)  # ValueError on <35 rows -> mapped to 422 globally
    return result, last_bar_at, latest_close


def _load_fundamental_result(db: Session, stock: Stock, latest_price=None):
    snapshots = load_fundamental_snapshots(db, stock.id, PeriodType.ANNUAL, limit=_FUNDAMENTAL_SNAPSHOT_LIMIT)
    if not snapshots:
        raise InsufficientDataError(f"No fundamental data available for '{stock.symbol}'")
    prior = snapshots[1] if len(snapshots) > 1 else None
    result = FundamentalAnalysisEngine().analyze(snapshots[0], prior_facts=prior, market_price=latest_price)
    return result, snapshots[0].fiscal_period_end


@router.get("/{symbol}/technical", response_model=Envelope[TechnicalAnalysisResponse])
def get_technical_analysis(
    symbol: str,
    request: Request,
    stock: Stock = Depends(get_stock_or_404),
    db: Session = Depends(get_db),
    principal: str = Depends(get_current_principal),
) -> Envelope[TechnicalAnalysisResponse]:
    result, last_bar_at, _ = _load_technical_result(db, stock)
    indicators = [
        IndicatorSummary(name=output.name, category=output.category.value, latest=output.latest())
        for output in result.indicators.values()
    ]
    data = TechnicalAnalysisResponse(symbol=symbol, indicators=indicators)
    return Envelope(data=data, meta=_now_meta(request, last_bar_at))


@router.get("/{symbol}/fundamental", response_model=Envelope[FundamentalAnalysisResponse])
def get_fundamental_analysis(
    symbol: str,
    request: Request,
    stock: Stock = Depends(get_stock_or_404),
    db: Session = Depends(get_db),
    principal: str = Depends(get_current_principal),
) -> Envelope[FundamentalAnalysisResponse]:
    # Market price is loaded (never recomputed) only to let valuation ratios
    # (e.g. P/E) populate -- gracefully degrades to None if no price history
    # exists yet (load_price_bars' own documented "no data" case, an empty
    # DataFrame, not an exception). A genuine query/session failure is a
    # real error and is deliberately left to propagate to the global
    # exception handler (500), not silently swallowed as "no price data".
    price_df = load_price_bars(db, stock.id, Timeframe.ONE_DAY)
    latest_price = float(price_df["close"].iloc[-1]) if not price_df.empty else None

    result, fiscal_period_end = _load_fundamental_result(db, stock, latest_price=latest_price)
    ratios = [
        RatioSummary(name=output.name, category=output.category.value, latest=output.latest())
        for output in result.ratios.values()
    ]
    data = FundamentalAnalysisResponse(symbol=symbol, ratios=ratios)
    as_of_reference = datetime.combine(fiscal_period_end, datetime.min.time(), tzinfo=timezone.utc)
    return Envelope(data=data, meta=_now_meta(request, as_of_reference))


@router.get("/{symbol}/composite", response_model=Envelope[CompositeAnalysisResponse])
def get_composite_analysis(
    symbol: str,
    request: Request,
    stock: Stock = Depends(get_stock_or_404),
    db: Session = Depends(get_db),
    principal: str = Depends(get_current_principal),
) -> Envelope[CompositeAnalysisResponse]:
    now = datetime.now(timezone.utc)
    technical_result, _, latest_price = _load_technical_result(db, stock)
    envelopes = {"technical_analysis": build_envelope("technical_analysis", technical_result, as_of=now, now=now)}

    try:
        fundamental_result, _ = _load_fundamental_result(db, stock, latest_price=latest_price)
    except InsufficientDataError:
        # Composite tolerates a missing engine envelope by design (every
        # composite factor reads envelopes.get(...), never envelopes[...]) --
        # graceful degradation, not a new capability added here.
        pass
    else:
        envelopes["fundamental_analysis"] = build_envelope(
            "fundamental_analysis", fundamental_result, as_of=now, now=now
        )

    composite_result = CompositeIntelligenceEngine().analyze(envelopes)
    factors = [
        CompositeFactorSchema(
            name=output.name,
            category=output.category.value,
            value=output.value,
            completeness=output.completeness.value,
            agreement=output.agreement.value if output.agreement is not None else None,
            contributing_engines=output.contributing_engines,
            explanation=output.explanation,
        )
        for output in composite_result.factors.values()
    ]
    data = CompositeAnalysisResponse(symbol=symbol, factors=factors)
    return Envelope(data=data, meta=Meta(as_of=now, freshness="fresh", request_id=get_request_id(request)))


@router.get("/{symbol}/councils/technical", response_model=Envelope[CouncilAnalysisResponse])
def get_technical_council_analysis(
    symbol: str,
    request: Request,
    stock: Stock = Depends(get_stock_or_404),
    db: Session = Depends(get_db),
    principal: str = Depends(get_current_principal),
) -> Envelope[CouncilAnalysisResponse]:
    now = datetime.now(timezone.utc)
    technical_result, _, _ = _load_technical_result(db, stock)
    envelopes = {"technical_analysis": build_envelope("technical_analysis", technical_result, as_of=now, now=now)}

    council_result = CouncilEngine(council=Council.TECHNICAL).analyze(symbol, envelopes, include_all_statuses=True)
    experts = [
        ExpertResultSchema(
            expert_id=expert.expert_id,
            expert_name=expert.expert_name,
            council=expert.council.value,
            domain=expert.domain,
            symbol=expert.symbol,
            as_of=expert.as_of,
            direction=expert.direction.value,
            normalized_score=expert.normalized_score,
            confidence=expert.confidence,
            completeness=expert.completeness.value,
            freshness=expert.freshness.value,
            evidence=tuple(
                EvidenceItemSchema(
                    metric_name=item.metric_name,
                    observed_value=item.observed_value,
                    rule_id=item.rule_id,
                    contribution=item.contribution,
                )
                for item in expert.evidence
            ),
            contributing_metrics=expert.contributing_metrics,
            rule_ids=expert.rule_ids,
            warnings=expert.warnings,
            conflicts=expert.conflicts,
            limitations=expert.limitations,
            version=expert.version,
            metadata=dict(expert.metadata),
        )
        for expert in council_result.experts.values()
    ]
    data = CouncilAnalysisResponse(symbol=symbol, council=Council.TECHNICAL.value, experts=experts)
    return Envelope(data=data, meta=Meta(as_of=now, freshness="fresh", request_id=get_request_id(request)))
