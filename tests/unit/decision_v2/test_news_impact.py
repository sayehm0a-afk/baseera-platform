"""Unit tests for news_impact.py -- real, DB-only sentiment
classification, never fabricated."""

from src.analysis.decision_v2.news_impact import build_news_impact


class TestBuildNewsImpact:
    def test_no_news_sentiment_data_yields_no_relevant_news(self):
        impact, summary = build_news_impact(None)
        assert impact == "NO_RELEVANT_NEWS"
        assert "لا توجد" in summary

    def test_empty_dict_yields_no_relevant_news(self):
        impact, summary = build_news_impact({})
        assert impact == "NO_RELEVANT_NEWS"

    def test_null_sentiment_score_yields_no_relevant_news(self):
        impact, _ = build_news_impact({"sentiment_score": None, "article_count": 0})
        assert impact == "NO_RELEVANT_NEWS"

    def test_strongly_positive_sentiment_classifies_as_positive(self):
        impact, summary = build_news_impact({"sentiment_score": 0.6, "article_count": 3})
        assert impact == "POSITIVE"
        assert "إيجابي" in summary
        assert "3" in summary

    def test_strongly_negative_sentiment_classifies_as_negative(self):
        impact, summary = build_news_impact({"sentiment_score": -0.6, "article_count": 2})
        assert impact == "NEGATIVE"
        assert "سلبي" in summary

    def test_near_zero_sentiment_classifies_as_neutral_not_no_relevant_news(self):
        impact, summary = build_news_impact({"sentiment_score": 0.02, "article_count": 5})
        assert impact == "NEUTRAL"
        assert "محايد" in summary

    def test_sentiment_score_is_clamped_to_valid_range(self):
        impact, _ = build_news_impact({"sentiment_score": 5.0, "article_count": 1})
        assert impact == "POSITIVE"
