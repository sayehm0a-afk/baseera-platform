"""GET/POST /api/v1/news/* -- REST layer over
src.news_intelligence, following the same conventions as
src/api/routes/calibrations.py (staff-only for anything that spends
real quota/LLM budget, plain reads open to any authenticated user).

`POST /news/refresh` runs synchronously (no BackgroundTask) -- bounded
by the same request-scoped `limit` cap every other bounded-synchronous
route in this codebase uses (`/calibrations/{version}/validate`,
`/calibrations/indicator-attribution`), so it is never an unbounded
full-history replay by construction.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_market_provider
from src.api.schemas.news import (
    NewsEntityOut,
    NewsEventOut,
    NewsFeedOut,
    NewsRefreshOut,
    NewsRefreshRequest,
    SourceReliabilityListOut,
    SourceReliabilityOut,
)
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import NewsEntity, NewsEntityType, NewsEvent, NewsSourceReliability, StaffRole, User
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.news_intelligence.collection import NewsCollector
from src.news_intelligence.service import NewsIntelligenceService

router = APIRouter(prefix="/api/v1/news", tags=["news"])

_DEFAULT_FEED_LIMIT = 50


def _to_news_event_out(event: NewsEvent) -> NewsEventOut:
    return NewsEventOut(
        id=event.id, headline=event.headline, source=event.source,
        source_reliability_score=event.source_reliability_score, published_at=event.published_at,
        is_synthetic=event.is_synthetic, category=event.category.value if event.category else None,
        sentiment_score=event.sentiment_score, sentiment_label=event.sentiment_label.value if event.sentiment_label else None,
        confidence=event.confidence, explanation=event.explanation, short_term_impact=event.short_term_impact,
        medium_term_impact=event.medium_term_impact, long_term_impact=event.long_term_impact,
        price_impact_score=event.price_impact_score, risk_impact_score=event.risk_impact_score,
        volatility_impact_score=event.volatility_impact_score, duplicate_count=event.duplicate_count,
        analyzed_at=event.analyzed_at, analysis_model=event.analysis_model,
        entities=[
            NewsEntityOut(entity_type=e.entity_type.value, symbol=e.symbol, sector=e.sector, label=e.label)
            for e in event.entities
        ],
    )


@router.get("/market", response_model=NewsFeedOut)
def get_market_news(
    limit: int = Query(default=_DEFAULT_FEED_LIMIT, ge=1, le=200),
    session: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> NewsFeedOut:
    """Market-wide/government events -- no single company is the
    subject."""
    events = (
        session.query(NewsEvent)
        .join(NewsEntity, NewsEntity.news_event_id == NewsEvent.id)
        .filter(
            NewsEntity.entity_type.in_([NewsEntityType.MARKET_WIDE, NewsEntityType.GOVERNMENT]),
            NewsEvent.duplicate_of_id.is_(None),
        )
        .order_by(NewsEvent.published_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    return NewsFeedOut(symbol=None, total=len(events), events=[_to_news_event_out(e) for e in events])


@router.get("/sources", response_model=SourceReliabilityListOut)
def list_source_reliability(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT))
) -> SourceReliabilityListOut:
    rows: List[NewsSourceReliability] = session.query(NewsSourceReliability).order_by(NewsSourceReliability.source_name).all()
    return SourceReliabilityListOut(
        sources=[
            SourceReliabilityOut(
                source_name=r.source_name, reliability_score=r.reliability_score, articles_seen=r.articles_seen,
                notes=r.notes, updated_at=r.updated_at,
            )
            for r in rows
        ]
    )


@router.post("/refresh", response_model=NewsRefreshOut)
async def refresh_news(
    request: NewsRefreshRequest,
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
    current_user: User = Depends(require_staff_role(StaffRole.SUPPORT)),
) -> NewsRefreshOut:
    service = NewsIntelligenceService()
    collector = NewsCollector(market_provider=market_provider)
    summary = await service.refresh(session, collector, limit=request.limit, user_id=current_user.id)
    return NewsRefreshOut(
        collected=summary.collected, already_ingested=summary.already_ingested, duplicates=summary.duplicates,
        newly_analyzed=summary.newly_analyzed, analysis_unavailable=summary.analysis_unavailable,
        analyzer_available=service.analyzer_available,
    )


@router.get("/{symbol}", response_model=NewsFeedOut)
def get_symbol_news(
    symbol: str,
    limit: int = Query(default=_DEFAULT_FEED_LIMIT, ge=1, le=200),
    session: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> NewsFeedOut:
    """Every canonical news event tagged with this symbol, newest
    first -- including ones still awaiting analysis (`analyzed_at`
    null), not only the analyzed ones `get_symbol_sentiment()` (the
    decision-engine-facing aggregate) considers."""
    events = (
        session.query(NewsEvent)
        .join(NewsEntity, NewsEntity.news_event_id == NewsEvent.id)
        .filter(
            NewsEntity.entity_type == NewsEntityType.COMPANY, NewsEntity.symbol == symbol,
            NewsEvent.duplicate_of_id.is_(None),
        )
        .order_by(NewsEvent.published_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    return NewsFeedOut(symbol=symbol, total=len(events), events=[_to_news_event_out(e) for e in events])
