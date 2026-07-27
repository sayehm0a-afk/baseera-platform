"""Unit tests for the four extra-bag-driven contributors: News,
Macro, Insider Transactions, Sector Rotation. Each is unavailable by
default (no real vendor integrated) and scores correctly the moment
`context.extra` carries the documented shape -- these tests prove
both halves of that contract.
"""

from src.analysis.decision.contributors.external_factor_contributors import (
    InsiderTransactionScoreContributor,
    MacroEconomicScoreContributor,
    NewsSentimentScoreContributor,
    SectorRotationScoreContributor,
)
from src.analysis.recommendation.types import AnalysisContext, SignalDirection


def _context(extra=None):
    return AnalysisContext(symbol="2222", extra=extra or {})


# --- News sentiment ------------------------------------------------------


def test_news_unavailable_by_default():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(_context())
    assert contribution.source == "news_sentiment"
    assert contribution.score is None
    assert contribution.weight == 0.0
    assert "news" in contribution.notes.lower()


def test_news_positive_sentiment_is_bullish():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(
        _context({"news_sentiment": {"sentiment_score": 0.5, "article_count": 5}})
    )
    assert contribution.score == 60.0
    assert contribution.weight == 0.05
    assert contribution.confidence == 100.0
    sig = contribution.signals[0]
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_news_negative_sentiment_is_bearish():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(
        _context({"news_sentiment": {"sentiment_score": -0.8, "article_count": 2}})
    )
    assert contribution.score == 34.0
    assert contribution.confidence == 40.0
    assert contribution.signals[0].direction == SignalDirection.BEARISH


def test_news_sentiment_is_clamped_to_valid_range():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(
        _context({"news_sentiment": {"sentiment_score": 5.0, "article_count": 10}})
    )
    assert contribution.score == 70.0  # 50 + clamp(5.0, -1, 1)*20 = 50+20


def test_news_sentiment_with_events_emits_one_signal_per_event():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(
        _context(
            {
                "news_sentiment": {
                    "sentiment_score": 0.5, "article_count": 2,
                    "events": [
                        {
                            "news_event_id": 1, "headline": "Aramco reports record earnings",
                            "category": "EARNINGS", "sentiment_score": 0.8, "confidence": 90.0, "impact_points": 8.0,
                        },
                        {
                            "news_event_id": 2, "headline": "New government infrastructure project awarded",
                            "category": "CONTRACT_AWARD", "sentiment_score": 0.4, "confidence": 70.0, "impact_points": 5.0,
                        },
                    ],
                }
            }
        )
    )
    # The blended score/confidence math is unchanged -- only the signals differ.
    assert contribution.score == 60.0
    assert contribution.confidence == 40.0
    assert len(contribution.signals) == 2
    assert contribution.signals[0].impact == 8.0
    assert contribution.signals[0].direction == SignalDirection.BULLISH
    assert "Earnings news (+8.0 pts)" in contribution.signals[0].description
    assert "Aramco reports record earnings" in contribution.signals[0].description
    assert contribution.signals[1].impact == 5.0
    assert "Contract Award news (+5.0 pts)" in contribution.signals[1].description


def test_news_sentiment_events_signal_direction_follows_impact_sign():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(
        _context(
            {
                "news_sentiment": {
                    "sentiment_score": -0.3, "article_count": 1,
                    "events": [
                        {
                            "news_event_id": 3, "headline": "Company faces lawsuit", "category": "LAWSUIT",
                            "sentiment_score": -0.6, "confidence": 80.0, "impact_points": -6.0,
                        },
                    ],
                }
            }
        )
    )
    assert contribution.signals[0].direction == SignalDirection.BEARISH
    assert "(-6.0 pts)" in contribution.signals[0].description


def test_news_sentiment_empty_events_list_falls_back_to_the_aggregate_signal():
    contributor = NewsSentimentScoreContributor()
    contribution = contributor.contribute(
        _context({"news_sentiment": {"sentiment_score": 0.5, "article_count": 5, "events": []}})
    )
    assert len(contribution.signals) == 1
    assert contribution.signals[0].name == "news_sentiment"


# --- Macro economy -----------------------------------------------------


def test_macro_unavailable_by_default():
    contributor = MacroEconomicScoreContributor()
    contribution = contributor.contribute(_context())
    assert contribution.score is None
    assert contribution.weight == 0.0


def test_macro_all_tailwinds_is_bullish():
    contributor = MacroEconomicScoreContributor()
    contribution = contributor.contribute(
        _context(
            {
                "macro_indicators": {
                    "tadawul_index_trend": "up",
                    "oil_price_trend": "up",
                    "interest_rate_trend": "down",
                }
            }
        )
    )
    # +6 (index up) + 5 (oil up) + 4 (rates down) = +15
    assert contribution.score == 65.0
    assert contribution.confidence == 100.0
    assert len(contribution.signals) == 3


def test_macro_partial_indicators_lowers_confidence():
    contributor = MacroEconomicScoreContributor()
    contribution = contributor.contribute(
        _context({"macro_indicators": {"tadawul_index_trend": "up"}})
    )
    assert contribution.confidence == round(100.0 / 3, 1)
    assert contribution.score == 56.0


def test_macro_unrecognized_keys_only_is_unavailable():
    contributor = MacroEconomicScoreContributor()
    contribution = contributor.contribute(
        _context({"macro_indicators": {"unrelated_key": "up"}})
    )
    assert contribution.score is None
    assert contribution.weight == 0.0


def test_macro_rising_rates_is_bearish():
    contributor = MacroEconomicScoreContributor()
    contribution = contributor.contribute(
        _context({"macro_indicators": {"interest_rate_trend": "up"}})
    )
    assert contribution.signals[0].direction == SignalDirection.BEARISH
    assert contribution.signals[0].impact == -4.0


# --- Insider transactions ------------------------------------------------


def test_insider_unavailable_by_default():
    contributor = InsiderTransactionScoreContributor()
    contribution = contributor.contribute(_context())
    assert contribution.score is None
    assert contribution.weight == 0.0


def test_insider_large_net_buying_is_strongly_bullish():
    contributor = InsiderTransactionScoreContributor()
    contribution = contributor.contribute(
        _context({"insider_transactions": {"net_buy_value": 2_000_000, "transaction_count": 4}})
    )
    assert contribution.signals[0].direction == SignalDirection.BULLISH
    assert contribution.signals[0].impact == 12.0
    assert contribution.confidence == 100.0


def test_insider_small_net_selling_is_mildly_bearish():
    contributor = InsiderTransactionScoreContributor()
    contribution = contributor.contribute(
        _context({"insider_transactions": {"net_buy_value": -50_000, "transaction_count": 1}})
    )
    assert contribution.signals[0].direction == SignalDirection.BEARISH
    assert contribution.signals[0].impact == -8.0
    assert contribution.confidence == 25.0


def test_insider_zero_net_activity_is_neutral():
    contributor = InsiderTransactionScoreContributor()
    contribution = contributor.contribute(
        _context({"insider_transactions": {"net_buy_value": 0, "transaction_count": 2}})
    )
    assert contribution.signals[0].direction == SignalDirection.NEUTRAL
    assert contribution.signals[0].impact == 0.0


# --- Sector rotation -----------------------------------------------------


def test_sector_rotation_unavailable_by_default():
    contributor = SectorRotationScoreContributor()
    contribution = contributor.contribute(_context())
    assert contribution.score is None
    assert contribution.weight == 0.0


def test_sector_outperformance_is_bullish():
    contributor = SectorRotationScoreContributor()
    contribution = contributor.contribute(
        _context({"sector_rotation": {"sector_relative_strength": 0.5}})
    )
    assert contribution.score == 60.0
    assert contribution.confidence == 75.0
    assert contribution.signals[0].direction == SignalDirection.BULLISH


def test_sector_underperformance_is_bearish():
    contributor = SectorRotationScoreContributor()
    contribution = contributor.contribute(
        _context({"sector_rotation": {"sector_relative_strength": -0.5}})
    )
    assert contribution.score == 40.0
    assert contribution.signals[0].direction == SignalDirection.BEARISH


# --- Weight configurability (all four) ------------------------------------


def test_all_four_contributors_have_configurable_weights():
    for cls, key, payload in [
        (NewsSentimentScoreContributor, "news_sentiment", {"sentiment_score": 0.1, "article_count": 1}),
        (MacroEconomicScoreContributor, "macro_indicators", {"tadawul_index_trend": "up"}),
        (InsiderTransactionScoreContributor, "insider_transactions", {"net_buy_value": 1, "transaction_count": 1}),
        (SectorRotationScoreContributor, "sector_rotation", {"sector_relative_strength": 0.1}),
    ]:
        contributor = cls(weight=0.42)
        contribution = contributor.contribute(_context({key: payload}))
        assert contribution.weight == 0.42
