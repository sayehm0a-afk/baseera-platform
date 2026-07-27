"""deduplication.py: detects duplicate/syndicated/updated-version
articles among newly collected items and against already-persisted
canonical NewsEvents -- pure functions, no network, no LLM, no
database. Two articles are the same underlying story when their
normalized headlines are near-identical (a syndicated copy, or a
lightly-edited "updated" version of the same wire item), not merely
because they are about the same symbol -- two genuinely distinct
stories about the same company are not duplicates.
"""

import difflib
import hashlib
import re
from typing import List, Optional

from src.news_intelligence.config import get_news_dedup_similarity_threshold
from src.news_intelligence.types import CanonicalCandidate, DedupResult, RawNewsItem

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_headline(headline: str) -> str:
    return _WHITESPACE_RE.sub(" ", headline.strip().lower())


def external_key(source: str, headline: str, published_at) -> str:
    """A stable idempotency key for one raw article: re-ingesting the
    exact same (source, normalized headline, published_at) triple
    always produces the same key, which is what
    `NewsEvent.external_key`'s unique constraint relies on to make
    re-ingestion a no-op rather than a duplicate row or a re-spent LLM
    call."""
    basis = f"{source}|{normalize_headline(headline)}|{published_at.isoformat() if published_at else ''}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:64]


def headline_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_headline(a), normalize_headline(b)).ratio()


def find_duplicate(
    item: RawNewsItem, candidates: List[CanonicalCandidate], threshold: Optional[float] = None
) -> DedupResult:
    """`candidates` is the set of already-persisted canonical events the
    caller considers plausibly related (typically: same recognized
    entity, published within `config.get_news_dedup_lookback_hours()`).
    Returns the best-matching candidate at or above the similarity
    threshold, or a non-duplicate result."""
    threshold = threshold if threshold is not None else get_news_dedup_similarity_threshold()

    best: Optional[CanonicalCandidate] = None
    best_score = 0.0
    for candidate in candidates:
        score = headline_similarity(item.headline, candidate.headline)
        if score >= threshold and score > best_score:
            best, best_score = candidate, score

    if best is None:
        return DedupResult(is_duplicate=False)
    return DedupResult(is_duplicate=True, canonical_event_id=best.id, similarity=best_score)
