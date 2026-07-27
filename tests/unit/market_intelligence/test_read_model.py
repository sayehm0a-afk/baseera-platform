"""Unit tests for read_model.outcome_from_record."""

from datetime import datetime, timezone
from decimal import Decimal

from src.domain.models import RecommendationLabel, SymbolIntelligenceRecord
from src.market_intelligence.read_model import outcome_from_record


def _record(**overrides):
    defaults = dict(
        scan_run_id=1, stock_id=1, symbol="2222", sector="Energy",
        recommendation=RecommendationLabel.BUY, confidence=Decimal("70.0"), final_score=Decimal("65.0"),
        target_price=Decimal("105.0"), stop_loss=Decimal("97.0"), expected_return_pct=Decimal("5.0"),
        risk_level="MEDIUM", time_horizon="MEDIUM_TERM", position_size="STANDARD",
        technical_score=Decimal("60.0"), fundamental_score=Decimal("55.0"), dividend_yield=Decimal("0.04"),
        rsi=Decimal("55.0"), adx=Decimal("28.0"), latest_price=Decimal("100.0"), bollinger_upper=Decimal("102.0"),
        bullish_factors=["Bullish."], bearish_factors=["Bearish."],
        evaluated_at=datetime.now(timezone.utc), engine_version="1.0.0",
    )
    defaults.update(overrides)
    return SymbolIntelligenceRecord(**defaults)


def test_reconstructs_decision_level_fields_faithfully():
    outcome = outcome_from_record(_record())
    assert outcome.symbol == "2222"
    assert outcome.sector == "Energy"
    assert outcome.success is True
    assert outcome.recommendation.value == "BUY"
    assert outcome.confidence == 70.0
    assert outcome.final_score == 65.0
    assert outcome.target_price == 105.0
    assert outcome.expected_return_pct == 5.0
    assert outcome.risk_level.value == "MEDIUM"


def test_reconstructs_technical_and_fundamental_scores_via_breakdown():
    outcome = outcome_from_record(_record())
    assert outcome.technical_score == 60.0
    assert outcome.fundamental_score == 55.0


def test_reconstructs_indicator_and_yield_fields():
    outcome = outcome_from_record(_record())
    assert outcome.rsi == 55.0
    assert outcome.adx == 28.0
    assert outcome.bollinger_upper == 102.0
    assert outcome.dividend_yield == 0.04
    assert outcome.latest_price == 100.0


def test_reconstructs_bullish_and_bearish_factors():
    outcome = outcome_from_record(_record())
    assert outcome.report.explanation.bullish_factors == ["Bullish."]
    assert outcome.report.explanation.bearish_factors == ["Bearish."]


def test_handles_missing_optional_fields_gracefully():
    outcome = outcome_from_record(
        _record(technical_score=None, fundamental_score=None, rsi=None, adx=None, bollinger_upper=None, dividend_yield=None)
    )
    assert outcome.technical_score is None
    assert outcome.fundamental_score is None
    assert outcome.rsi is None
    assert outcome.dividend_yield is None
    assert outcome.technical_snapshot is None
