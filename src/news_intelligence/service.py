"""service.py: NewsIntelligenceService -- orchestrates the full
pipeline (collect -> dedup -> analyze -> persist) and answers the one
question the decision engine actually needs at request time: "what is
this symbol's current news sentiment." The two are deliberately split
in cost: `refresh()` is the expensive path (network + LLM calls),
meant to run on a schedule (mirroring `IngestionScheduler`'s pattern),
while `get_symbol_sentiment()` is a cheap, synchronous, DB-only read
-- called from `context_builder.build_analysis_context()` on every
recommendation/decision/scan/portfolio request, so it must never touch
the network or an LLM itself.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.domain.models import NewsCategory, NewsEntity, NewsEntityType, NewsEvent, Stock
from src.news_intelligence.analyzer import NewsAnalyzer
from src.news_intelligence.collection import NewsCollector
from src.news_intelligence.config import (
    get_max_events_per_symbol_sentiment,
    get_news_dedup_lookback_hours,
    get_news_sentiment_lookback_days,
)
from src.news_intelligence.deduplication import external_key, find_duplicate
from src.news_intelligence.source_reliability import SourceReliabilityService
from src.news_intelligence.types import (
    CanonicalCandidate,
    NewsEventSummary,
    RawNewsItem,
    RefreshSummary,
    SymbolNewsSentiment,
)

logger = logging.getLogger(__name__)

# The same points-per-unit-sentiment scale NewsSentimentScoreContributor
# already uses for its own aggregate signal -- individual per-event
# Signals (see the contributor) must land on the same scale so
# AIDecisionEngine's "top signals by impact" ranking is fair between
# the aggregate and the per-event breakdown.
_SENTIMENT_POINTS_SCALE = 20.0


class NewsIntelligenceService:
    def __init__(self, analyzer: Optional[NewsAnalyzer] = None, source_reliability: Optional[SourceReliabilityService] = None):
        self._analyzer = analyzer if analyzer is not None else NewsAnalyzer()
        self._source_reliability = source_reliability if source_reliability is not None else SourceReliabilityService()

    @property
    def analyzer_available(self) -> bool:
        return self._analyzer.is_available

    async def refresh(
        self, session: Session, collector: NewsCollector, limit: Optional[int] = None, user_id: Optional[int] = None
    ) -> RefreshSummary:
        """Collects the latest news, deduplicates against recently
        persisted canonical events, analyzes only genuinely new
        articles, and persists everything. Idempotent: re-running
        immediately after a successful run collects the same items
        again (the provider has no cursor) but every one is recognized
        as `already_ingested` via `external_key` and skipped -- no
        duplicate row, no re-spent LLM call."""
        items = await collector.collect(limit=limit)
        already_ingested = 0
        duplicates = 0
        newly_analyzed = 0
        analysis_unavailable = 0

        cutoff = datetime.now(timezone.utc) - timedelta(hours=get_news_dedup_lookback_hours())
        candidates = self._recent_canonical_candidates(session, cutoff)

        for item in items:
            key = external_key(item.source, item.headline, item.timestamp)
            if session.query(NewsEvent.id).filter_by(external_key=key).first() is not None:
                already_ingested += 1
                continue

            dedup_result = find_duplicate(item, candidates)
            if dedup_result.is_duplicate:
                self._persist_duplicate(session, item, key, dedup_result.canonical_event_id)
                duplicates += 1
                continue

            event = await self._persist_canonical(session, item, key, user_id)
            candidates.append(CanonicalCandidate(id=event.id, headline=event.headline))
            if event.analyzed_at is not None:
                newly_analyzed += 1
            else:
                analysis_unavailable += 1

        return RefreshSummary(
            collected=len(items), already_ingested=already_ingested, duplicates=duplicates,
            newly_analyzed=newly_analyzed, analysis_unavailable=analysis_unavailable,
        )

    def _recent_canonical_candidates(self, session: Session, cutoff: datetime) -> List[CanonicalCandidate]:
        rows = (
            session.query(NewsEvent.id, NewsEvent.headline)
            .filter(NewsEvent.duplicate_of_id.is_(None))
            .filter((NewsEvent.published_at >= cutoff) | (NewsEvent.published_at.is_(None)))
            .all()
        )
        return [CanonicalCandidate(id=row.id, headline=row.headline) for row in rows]

    def _persist_duplicate(self, session: Session, item: RawNewsItem, key: str, canonical_id: int) -> None:
        session.add(
            NewsEvent(
                external_key=key, headline=item.headline, source=item.source, published_at=item.timestamp,
                is_synthetic=item.is_synthetic, duplicate_of_id=canonical_id, raw_payload=item.raw,
            )
        )
        canonical = session.get(NewsEvent, canonical_id)
        if canonical is not None:
            canonical.duplicate_count += 1
        session.commit()

    async def _persist_canonical(self, session: Session, item: RawNewsItem, key: str, user_id: Optional[int]) -> NewsEvent:
        self._source_reliability.record_article_seen(session, item.source)
        reliability_score = self._source_reliability.get_score(session, item.source)

        analysis = await self._analyzer.analyze(item, session=session, user_id=user_id)

        event = NewsEvent(
            external_key=key, headline=item.headline, source=item.source,
            source_reliability_score=reliability_score, published_at=item.timestamp, is_synthetic=item.is_synthetic,
            raw_payload=item.raw,
        )
        if analysis is not None:
            event.category = analysis.category
            event.sentiment_score = analysis.sentiment_score
            event.sentiment_label = analysis.sentiment_label
            event.confidence = analysis.confidence
            event.explanation = analysis.explanation
            event.short_term_impact = analysis.impact.short_term
            event.medium_term_impact = analysis.impact.medium_term
            event.long_term_impact = analysis.impact.long_term
            event.price_impact_score = analysis.impact.price_impact
            event.risk_impact_score = analysis.impact.risk_impact
            event.volatility_impact_score = analysis.impact.volatility_impact
            event.analyzed_at = datetime.now(timezone.utc)
            event.analysis_model = analysis.model

        session.add(event)
        session.flush()

        if analysis is not None:
            for entity in analysis.entities:
                stock_id = None
                if entity.entity_type is NewsEntityType.COMPANY and entity.symbol:
                    stock = session.query(Stock).filter_by(symbol=entity.symbol).one_or_none()
                    stock_id = stock.id if stock is not None else None
                session.add(
                    NewsEntity(
                        news_event_id=event.id, entity_type=entity.entity_type, stock_id=stock_id,
                        symbol=entity.symbol, sector=entity.sector, label=entity.label,
                    )
                )

        session.commit()
        return event

    def get_symbol_sentiment(
        self, session: Session, symbol: str, lookback_days: Optional[int] = None
    ) -> Optional[SymbolNewsSentiment]:
        """A cheap, synchronous, DB-only read -- no network, no LLM.
        Aggregates every canonical, analyzed event tagged with this
        symbol within the lookback window into the exact shape
        `NewsSentimentScoreContributor` expects, plus a per-event
        breakdown for explainability. Market-wide/sector-only events
        are not yet blended into a single symbol's sentiment -- a
        disclosed scope boundary (see docs/NEWS_INTELLIGENCE.md), not
        an oversight; they remain queryable via the market-wide news
        endpoint on their own.
        """
        lookback = lookback_days if lookback_days is not None else get_news_sentiment_lookback_days()
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback)

        rows = (
            session.query(NewsEvent)
            .join(NewsEntity, NewsEntity.news_event_id == NewsEvent.id)
            .filter(
                NewsEntity.entity_type == NewsEntityType.COMPANY,
                NewsEntity.symbol == symbol,
                NewsEvent.duplicate_of_id.is_(None),
                NewsEvent.analyzed_at.isnot(None),
                NewsEvent.published_at >= cutoff,
            )
            .order_by(NewsEvent.published_at.desc())
            .all()
        )
        if not rows:
            return None

        weighted_sum = 0.0
        weight_total = 0.0
        for event in rows:
            weight = (event.confidence or 0.0) / 100.0 * (event.source_reliability_score or 0.0)
            weighted_sum += (event.sentiment_score or 0.0) * weight
            weight_total += weight
        aggregate_sentiment = max(-1.0, min(1.0, weighted_sum / weight_total)) if weight_total > 0 else 0.0

        ranked = sorted(rows, key=lambda e: abs((e.sentiment_score or 0.0) * (e.confidence or 0.0)), reverse=True)
        top_events = [
            NewsEventSummary(
                news_event_id=event.id, headline=event.headline,
                category=event.category or NewsCategory.OTHER, sentiment_score=event.sentiment_score or 0.0,
                confidence=event.confidence or 0.0,
                impact_points=round(
                    (event.sentiment_score or 0.0) * _SENTIMENT_POINTS_SCALE * ((event.confidence or 0.0) / 100.0), 1
                ),
            )
            for event in ranked[: get_max_events_per_symbol_sentiment()]
        ]

        return SymbolNewsSentiment(sentiment_score=aggregate_sentiment, article_count=len(rows), events=top_events)
