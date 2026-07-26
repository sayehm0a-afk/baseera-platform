"""source_reliability.py: SourceReliabilityService -- every source the
News Intelligence Engine has ever ingested from gets a durable,
queryable reliability score (`NewsSourceReliability`). An unknown
source gets a conservative default on first sight, never a fabricated
"trusted" score. `record_article_seen()` is called once per newly
collected *canonical* article -- never once per syndicated duplicate
-- so a source's article count reflects distinct stories, not how many
outlets re-ran the same wire item; this is the mechanism behind
"duplicate or recycled news must not increase confidence."
"""

from typing import Optional

from sqlalchemy.orm import Session

from src.domain.models import NewsSourceReliability
from src.news_intelligence.config import get_default_source_reliability


class SourceReliabilityService:
    def get_or_create(self, session: Session, source_name: str) -> NewsSourceReliability:
        row = session.query(NewsSourceReliability).filter_by(source_name=source_name).one_or_none()
        if row is None:
            row = NewsSourceReliability(source_name=source_name, reliability_score=get_default_source_reliability())
            session.add(row)
            session.flush()
        return row

    def record_article_seen(self, session: Session, source_name: str) -> NewsSourceReliability:
        row = self.get_or_create(session, source_name)
        row.articles_seen += 1
        session.flush()
        return row

    def set_reliability(
        self, session: Session, source_name: str, score: float, notes: Optional[str] = None
    ) -> NewsSourceReliability:
        """A manual override -- an operator's own judgment about a
        source's trustworthiness, distinct from the automatic default.
        Clamped to [0, 1]."""
        row = self.get_or_create(session, source_name)
        row.reliability_score = max(0.0, min(1.0, score))
        if notes is not None:
            row.notes = notes
        session.flush()
        return row

    def get_score(self, session: Session, source_name: str) -> float:
        row = session.query(NewsSourceReliability).filter_by(source_name=source_name).one_or_none()
        return row.reliability_score if row is not None else get_default_source_reliability()
