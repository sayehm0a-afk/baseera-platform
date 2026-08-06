"""Section 11: a per-recommendation news-impact classification for
Decision Engine V2 -- POSITIVE / NEGATIVE / NEUTRAL / NO_RELEVANT_NEWS.

Reads exclusively from `context.extra["news_sentiment"]`, the exact
dict shape `src.analysis.context_builder._news_sentiment_extra` already
populates from `NewsIntelligenceService.get_symbol_sentiment()` (a
real, DB-only aggregate over analyzed `NewsEvent` rows -- see that
service's own docstring) and that
`NewsSentimentScoreContributor` already scores with. This module adds
no new news collection/analysis of its own; it only classifies an
already-computed sentiment score into the discrete label a user reads,
the same way `NewsSentimentScoreContributor` turns it into a
continuous score. `NO_RELEVANT_NEWS` -- not `NEUTRAL` -- is the honest
label when no analyzed news exists for this symbol at all, distinct
from news existing but reading as sentiment-neutral.
"""

from typing import Any, Dict, Optional, Tuple

# Deliberately conservative: real sentiment noise sits close to 0 for
# most symbols on most days, so a low threshold would label routine,
# inconsequential coverage as POSITIVE/NEGATIVE. Not derived from a
# statistical study of this platform's own data (a disclosed judgment
# call), but a stricter bar than NewsSentimentScoreContributor's own
# scoring (which is continuous and needs no threshold).
_POSITIVE_THRESHOLD = 0.15
_NEGATIVE_THRESHOLD = -0.15

_IMPACT_LABELS_AR = {"POSITIVE": "إيجابي", "NEGATIVE": "سلبي", "NEUTRAL": "محايد"}


def build_news_impact(news_sentiment: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """Returns (news_impact, news_impact_summary_ar)."""
    if not news_sentiment or news_sentiment.get("sentiment_score") is None:
        return "NO_RELEVANT_NEWS", "لا توجد أخبار محلَّلة حديثة ذات صلة بهذا السهم."

    sentiment = max(-1.0, min(1.0, float(news_sentiment["sentiment_score"])))
    article_count = int(news_sentiment.get("article_count", 0) or 0)

    if sentiment > _POSITIVE_THRESHOLD:
        impact = "POSITIVE"
    elif sentiment < _NEGATIVE_THRESHOLD:
        impact = "NEGATIVE"
    else:
        impact = "NEUTRAL"

    summary = f"الأثر الإخباري {_IMPACT_LABELS_AR[impact]} (درجة الشعور {sentiment:+.2f} عبر {article_count} خبرًا محلَّلاً)."
    return impact, summary
