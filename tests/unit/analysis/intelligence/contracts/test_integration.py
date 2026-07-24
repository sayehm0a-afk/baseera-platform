"""Unit tests for build_recommendation_input -- pure data-shaping, no
computation."""

from datetime import datetime, timezone

from src.analysis.intelligence.contracts.integration import build_recommendation_input
from src.market_data.models import MarketQuote, RecommendationInput


def test_build_recommendation_input_packages_given_values():
    now = datetime.now(timezone.utc)
    quote = MarketQuote(symbol="1010", price=42.0, change=1.0, change_percent=2.4, volume=1000, timestamp=now)

    result = build_recommendation_input(symbol="1010", as_of=now, quote=quote)

    assert isinstance(result, RecommendationInput)
    assert result.symbol == "1010"
    assert result.quote is quote
    assert result.as_of is now


def test_build_recommendation_input_defaults_lists_to_empty_not_none():
    now = datetime.now(timezone.utc)
    result = build_recommendation_input(symbol="1010", as_of=now)
    assert result.technical_indicators == []
    assert result.fundamental_ratios == []
    assert result.quote is None
    assert result.profile is None
