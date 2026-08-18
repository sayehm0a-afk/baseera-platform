"""RADAR-C Phase C: tests for the three new evidence-backed confidence
caps added to DecisionEngineV2.decide() -- market regime CAUTION,
graduated volatility, and news-direction contradiction. Follows the
exact fixture pattern tests/unit/decision_v2/test_engine.py already
established (real TechnicalAnalysisEngine over synthetic OHLCV, a
directly-built InvestmentDecision) plus test_market_risk.py's
MarketBreadthSummary helper, rather than inventing a new fixture style.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.analysis.decision.types import (
    DecisionFactorBreakdown,
    EntryQuality,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.engine import DecisionEngineV2
from src.analysis.recommendation.types import AnalysisContext, Recommendation
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.market_intelligence.types import MarketBreadthSummary


def _make_ohlcv(n=90, seed=1, std=1.0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, std, n))
    high = close + np.abs(rng.normal(0, std * 0.3 + 0.001, n))
    low = close - np.abs(rng.normal(0, std * 0.3 + 0.001, n))
    open_ = close + rng.normal(0, std * 0.2, n)
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def _technical(std=1.0, seed=1):
    return TechnicalAnalysisEngine().analyze(_make_ohlcv(std=std, seed=seed))


def _context(price=100.0, technical=None, extra=None):
    return AnalysisContext(
        symbol="2222", technical_result=technical if technical is not None else _technical(),
        fundamental_result=None, latest_price=price, extra=extra or {},
    )


def _buy_decision(price=100.0, target=112.0, stop=94.0, confidence=95.0) -> InvestmentDecision:
    return InvestmentDecision(
        symbol="2222",
        recommendation=Recommendation.BUY,
        confidence=confidence,
        final_score=68.0,
        target_price=target,
        stop_loss=stop,
        time_horizon=TimeHorizon.SHORT_TERM,
        expected_return_pct=round((target - price) / price * 100, 2),
        risk_level=RiskLevel.MEDIUM,
        position_size=PositionSize.STANDARD,
        reasons=["نمط فني إيجابي عام."],
        breakdown=[DecisionFactorBreakdown(category="Technical Analysis", points=18.0, weight=0.6, confidence=90.0, available=True)],
        signals=[],
        generated_at=datetime.now(timezone.utc),
        entry_quality=EntryQuality.GOOD,
        risk_reward_ratio=round((target - price) / (price - stop), 2),
    )


def _breadth(buy, sell, scanned=30, confidence=60.0) -> MarketBreadthSummary:
    return MarketBreadthSummary(
        scan_run_id=1, generated_at=datetime.now(timezone.utc),
        symbols_scanned=scanned, buy_count=buy, sell_count=sell, average_confidence=confidence,
    )


def _decide(ctx, decision, **overrides):
    kwargs = dict(
        company_name_ar="أرامكو السعودية",
        company_name_en="Saudi Aramco",
        sector="Energy",
        sector_ar="الطاقة",
        is_synthetic=False,
        data_source="SAHMK",
        quote_timestamp=datetime.now(timezone.utc),
        market_status="OPEN",
        market_is_open=True,
        scan_run_id=None,
        market_breadth=None,
    )
    kwargs.update(overrides)
    return DecisionEngineV2().decide(ctx, decision, **kwargs)


class TestMarketCautionConfidenceCap:
    def test_caution_regime_caps_confidence_below_the_tuning_ceiling(self):
        ctx = _context()
        # buy_ratio = 38/(38+62) = 0.38 -> within market_risk.py's
        # CAUTION band [0.35, 0.45).
        result = _decide(ctx, _buy_decision(), market_breadth=_breadth(buy=38, sell=62))
        assert result.confidence_score <= DecisionV2Tuning().market_caution_confidence_cap
        assert any("حذر" in w for w in result.warnings)

    def test_neutral_regime_is_not_capped_by_the_caution_rule(self):
        ctx = _context()
        # buy_ratio = 50/100 = 0.50 -> NEUTRAL, not CAUTION.
        result = _decide(ctx, _buy_decision(), market_breadth=_breadth(buy=50, sell=50))
        assert not any("حذر" in w for w in result.warnings if "مخاطر السوق الحالية تدعو" in w)


class TestVolatilityConfidenceCap:
    def test_very_low_volatility_caps_confidence_below_a_normal_volatility_setup(self):
        # An almost-flat price series -> ATR% far below the sweet spot
        # -> a low volatility_score -> the graduated cap should engage.
        low_vol_ctx = _context(technical=_technical(std=0.02, seed=2))
        normal_vol_ctx = _context(technical=_technical(std=1.0, seed=1))
        low_vol_result = _decide(low_vol_ctx, _buy_decision())
        normal_vol_result = _decide(normal_vol_ctx, _buy_decision())
        assert low_vol_result.confidence_score < normal_vol_result.confidence_score

    def test_capped_confidence_never_exceeds_100_or_goes_negative(self):
        ctx = _context(technical=_technical(std=0.02, seed=2))
        result = _decide(ctx, _buy_decision(confidence=100.0))
        assert 0.0 <= result.confidence_score <= 100.0


class TestNewsContradictionConfidenceCap:
    def test_negative_news_on_a_buy_decision_caps_confidence(self):
        ctx = _context(extra={"news_sentiment": {"sentiment_score": -0.8, "article_count": 5}})
        result = _decide(ctx, _buy_decision())
        assert result.news_impact == "NEGATIVE"
        assert result.confidence_score <= DecisionV2Tuning().contradictory_news_confidence_cap
        assert any("الأثر الإخباري" in w for w in result.warnings)

    def test_positive_news_on_a_buy_decision_is_not_capped_by_the_contradiction_rule(self):
        ctx = _context(extra={"news_sentiment": {"sentiment_score": 0.8, "article_count": 5}})
        result = _decide(ctx, _buy_decision())
        assert result.news_impact == "POSITIVE"
        assert not any("الأثر الإخباري" in w for w in result.warnings)

    def test_no_relevant_news_is_not_capped(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.news_impact == "NO_RELEVANT_NEWS"
        assert not any("الأثر الإخباري" in w for w in result.warnings)


@pytest.mark.parametrize(
    "breadth,extra",
    [
        (_breadth(buy=38, sell=62), {"news_sentiment": {"sentiment_score": -0.8, "article_count": 3}}),
    ],
)
class TestStackedRadarCCaps:
    def test_multiple_new_caps_stack_without_escaping_bounds(self, breadth, extra):
        ctx = _context(technical=_technical(std=0.02, seed=2), extra=extra)
        result = _decide(ctx, _buy_decision(confidence=100.0), market_breadth=breadth)
        assert 0.0 <= result.confidence_score <= 100.0
        assert result.confidence_score == result.confidence_score  # not NaN
