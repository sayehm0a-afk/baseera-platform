"""Shared, hand-built fixtures for Investment Committee unit tests --
a minimal real `InvestmentDecision` and `DecisionResult`, both
constructed with plain floats (not numpy) since these tests exercise
agent/consensus logic, not the numpy-coercion regression already
covered by test_market_intelligence_repository.py.
"""

from datetime import datetime, timezone

from src.analysis.decision.types import (
    DecisionFactorBreakdown, EntryQuality, InvestmentDecision, PositionSize, RiskLevel, TimeHorizon,
)
from src.analysis.decision_v2.types import DataFreshnessStatus, Decision, DecisionResult, SubScores
from src.analysis.recommendation.types import Recommendation


def breakdown(category, points=0.0, weight=0.25, confidence=80.0, available=True, notes=None):
    return DecisionFactorBreakdown(
        category=category, points=points, weight=weight, confidence=confidence, available=available, notes=notes
    )


def make_investment_decision(
    breakdown_items=None, position_size=PositionSize.STANDARD, risk_level=RiskLevel.MEDIUM, **overrides
) -> InvestmentDecision:
    defaults = dict(
        symbol="2222", recommendation=Recommendation.BUY, confidence=65.0, final_score=62.0,
        target_price=30.0, stop_loss=26.0, time_horizon=TimeHorizon.MEDIUM_TERM, expected_return_pct=8.0,
        risk_level=risk_level, position_size=position_size, reasons=["technical breakout"],
        breakdown=breakdown_items if breakdown_items is not None else [
            breakdown("Technical Analysis", points=15.0),
            breakdown("Fundamental Analysis", points=10.0),
            breakdown("Risk", points=8.0),
        ],
        signals=[], generated_at=datetime.now(timezone.utc), entry_quality=EntryQuality.GOOD,
    )
    defaults.update(overrides)
    return InvestmentDecision(**defaults)


def make_decision_result(**overrides) -> DecisionResult:
    defaults = dict(
        symbol="2222", company_name_ar="سهم", company_name_en="Stock 2222", sector_ar="الطاقة",
        decision=Decision.BUY_CANDIDATE, decision_label_ar="مرشح شراء",
        confidence_score=65.0, opportunity_quality_score=60.0, risk_score=35.0, data_quality_score=100.0,
        data_freshness_status=DataFreshnessStatus.LIVE,
        current_price=27.0, entry_zone_low=26.5, entry_zone_high=27.5, stop_loss=26.0,
        target_1=29.0, target_2=30.5, target_3=32.0,
        expected_return_target_1=7.4, expected_return_target_2=13.0, downside_to_stop=-3.7,
        risk_reward_target_1=2.0, risk_reward_target_2=3.5,
        expected_holding_period_min_days=5, expected_holding_period_max_days=30,
        expected_holding_period_label_ar="من أسبوع إلى شهر", horizon_type="MEDIUM_TERM",
        market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        invalidation_conditions=[], positive_reasons=[], negative_reasons=[], warnings=[],
        recommendation_basis="test", analysis_version="2.0.0", data_source="SAHMK_REAL", scan_run_id=None,
        sub_scores=SubScores(
            trend_score=60.0, momentum_score=55.0, volume_score=65.0, liquidity_score=70.0,
            volatility_score=40.0, risk_reward_score=64.0, market_context_score=60.0, data_quality_score=100.0,
        ),
        gates=[],
        fundamental_summary={
            "revenue_growth": 0.12, "profit_growth": 0.08, "net_profit_margin": 0.15, "gross_profit_margin": 0.4,
            "return_on_equity": 0.18, "debt_to_equity": 0.5, "price_to_earnings": 14.2, "price_to_book": 2.1,
            "dividend_yield": 0.03, "eps_growth": 0.1,
        },
        fundamental_summary_ar="الإيرادات في اتجاه تصاعدي.",
        trend_direction_ar="صاعد", trend_strength_label_ar="قوي",
        support_resistance_evidence_ar="دعم قريب عند 26.5",
        risk_level_label_ar="متوسطة",
        liquidity_confidence=70.0, relative_volume=1.3, liquidity_quality_ar="جيدة",
        accumulation_score=60.0, accumulation_assessment_ar="تجميع إيجابي ملحوظ.",
        volume_confirms_decision=True, abnormal_volume=False,
        entry_quality_label_ar="جيدة",
        market_risk_state="NORMAL", market_risk_label_ar="طبيعية", market_risk_basis_ar="اتساع سوق متوازن.",
        market_risk_entry_permitted=True, market_risk_is_live=True,
        market_breadth_buy_count=40, market_breadth_sell_count=20, market_breadth_symbols_scanned=100,
        market_breadth_average_confidence=58.0,
    )
    defaults.update(overrides)
    return DecisionResult(**defaults)
