"""types.py: pure data shapes for the News Intelligence Engine
pipeline -- collection, deduplication, analysis, source reliability,
and portfolio alerts all pass these dataclasses between stages before
a persistence step turns them into NewsEvent/NewsEntity/
PortfolioNewsAlert rows.

Reuses the DB layer's own enums (`NewsCategory`, `SentimentLabel`,
`NewsEntityType`, `PortfolioAlertType`) rather than a second, parallel
definition: unlike `src.analysis.recommendation`/`src.analysis.decision`
(genuinely DB-free engine layers with real architectural boundaries to
protect), this package is a data pipeline that reads and writes the
database at nearly every stage -- closer in shape to
`src.backtesting`/`src.market_intelligence`'s own `service.py`/
`repository.py` layers, which already mix engine logic and `Session`
freely. There is no boundary here worth the duplication.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.domain.models import AlertSeverity, NewsCategory, NewsEntityType, PortfolioAlertType, SentimentLabel


@dataclass(frozen=True)
class RawNewsItem:
    """One news item exactly as `IMarketDataProvider.get_market_news()`
    returns it, normalized to a typed shape. `source`/`is_synthetic`
    are always present (every registered provider -- sahmk and dev --
    already labels them); `symbol` is the provider's own best-effort
    tag, not yet the result of this engine's own entity recognition."""

    headline: str
    source: str
    is_synthetic: bool
    timestamp: Optional[datetime] = None
    symbol: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalCandidate:
    """A minimal projection of an already-persisted canonical NewsEvent
    -- everything deduplication.find_duplicate() needs to compare a new
    RawNewsItem against, without depending on the ORM model itself."""

    id: int
    headline: str


@dataclass(frozen=True)
class DedupResult:
    is_duplicate: bool
    canonical_event_id: Optional[int] = None
    similarity: float = 0.0


@dataclass(frozen=True)
class EntityMention:
    entity_type: NewsEntityType
    symbol: Optional[str] = None
    sector: Optional[str] = None
    label: Optional[str] = None


@dataclass(frozen=True)
class ImpactEstimate:
    """All six fields are -1..1 (direction and rough magnitude), except
    `price_impact`/`risk_impact`/`volatility_impact` which are 0..1
    magnitudes only (a lawsuit increases risk regardless of headline
    sentiment sign, for example -- risk/volatility are not directional
    the way price impact and the time-horizon impacts are)."""

    short_term: float
    medium_term: float
    long_term: float
    price_impact: float
    risk_impact: float
    volatility_impact: float


@dataclass(frozen=True)
class NewsAnalysisResult:
    """One headline's full analysis -- entities, category, sentiment,
    impact -- produced by the LLM analyzer. `model` stays `None` (and
    every other field is this dataclass's own honest, disclosed
    default: category OTHER, zero sentiment/impact, zero confidence)
    when analysis could not run at all (e.g. no `OPENAI_API_KEY`
    configured) -- never a fabricated classification standing in for a
    real one."""

    entities: List[EntityMention]
    category: NewsCategory
    sentiment_score: float
    sentiment_label: SentimentLabel
    confidence: float
    explanation: str
    impact: ImpactEstimate
    model: Optional[str] = None


@dataclass(frozen=True)
class NewsEventSummary:
    """One analyzed event's contribution to a symbol's aggregate
    sentiment -- the per-event explainability breakdown requirement 9
    asks for ("Positive earnings (+8)")."""

    news_event_id: int
    headline: str
    category: NewsCategory
    sentiment_score: float
    confidence: float
    impact_points: float


@dataclass(frozen=True)
class SymbolNewsSentiment:
    """The exact shape `NewsSentimentScoreContributor`'s
    `context.extra["news_sentiment"]` expects (`sentiment_score`,
    `article_count`), plus an `events` breakdown the contributor uses
    for per-event Signal explainability."""

    sentiment_score: float
    article_count: int
    events: List[NewsEventSummary] = field(default_factory=list)


@dataclass(frozen=True)
class RefreshSummary:
    """What one `NewsIntelligenceService.refresh()` call did -- the
    counters requirement 11's "no duplicated processing" claim is
    verifiable against."""

    collected: int
    already_ingested: int
    duplicates: int
    newly_analyzed: int
    analysis_unavailable: int


@dataclass(frozen=True)
class PortfolioAlert:
    portfolio_id: int
    symbol: str
    news_event_id: int
    alert_type: PortfolioAlertType
    severity: AlertSeverity
    message: str
    message_ar: str
    generated_at: datetime
    id: Optional[int] = None


@dataclass(frozen=True)
class WatchlistAlert:
    """The watchlist-side mirror of `PortfolioAlert` -- same shape,
    scoped to a `watchlist_id` instead of a `portfolio_id` (RADAR-C
    Phase I)."""

    watchlist_id: int
    symbol: str
    news_event_id: int
    alert_type: PortfolioAlertType
    severity: AlertSeverity
    message: str
    message_ar: str
    generated_at: datetime
    id: Optional[int] = None
