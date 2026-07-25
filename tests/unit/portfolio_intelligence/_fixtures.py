"""Small builder helpers shared by the Autonomous Portfolio
Intelligence Layer unit tests -- the same "hand-built fake data, not a
real engine run" technique tests/unit/market_intelligence/_fixtures.py
already uses, applied one layer up so each portfolio_intelligence
module can be tested in isolation from a real scan/analysis.
"""

from datetime import datetime, timezone
from typing import List, Optional

from src.analysis.analyst.types import AnalystReport, Explanation
from src.analysis.decision.types import (
    DecisionFactorBreakdown,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.recommendation.types import Recommendation
from src.portfolio_intelligence.types import HoldingAnalysis


def make_decision(
    symbol="2222",
    recommendation=Recommendation.BUY,
    confidence=70.0,
    final_score=65.0,
    target_price: Optional[float] = 105.0,
    risk_level=RiskLevel.MEDIUM,
    position_size=PositionSize.STANDARD,
    time_horizon=TimeHorizon.MEDIUM_TERM,
) -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol, recommendation=recommendation, confidence=confidence, final_score=final_score,
        target_price=target_price, stop_loss=95.0, time_horizon=time_horizon,
        expected_return_pct=5.0, risk_level=risk_level, position_size=position_size,
        reasons=[f"{recommendation.value} on {symbol}."],
        breakdown=[DecisionFactorBreakdown(category="Technical Analysis", points=15.0, weight=0.25, confidence=90.0, available=True)],
        signals=[], generated_at=datetime.now(timezone.utc),
    )


def make_report(symbol="2222", decision: Optional[InvestmentDecision] = None) -> AnalystReport:
    decision = decision or make_decision(symbol=symbol)
    explanation = Explanation(
        investment_summary="summary", technical_reasoning="tech", fundamental_reasoning="fund",
        risk_explanation="risk", bullish_factors=["Bullish."], bearish_factors=["Bearish."],
        confidence_explanation="conf", target_price_explanation="target", stop_loss_explanation="stop",
        time_horizon_explanation="horizon", alternative_scenarios=[], final_recommendation_rationale="final",
    )
    return AnalystReport(
        symbol=symbol, decision=decision, explanation=explanation,
        generated_at=datetime.now(timezone.utc), engine_version="1.0.0",
    )


def make_holding_analysis(
    symbol="2222",
    sector: Optional[str] = "Energy",
    quantity=100.0,
    average_cost: Optional[float] = 30.0,
    latest_price: Optional[float] = 40.0,
    weight: Optional[float] = 0.5,
    decision: Optional[InvestmentDecision] = None,
    report: Optional[AnalystReport] = None,
    unavailable: bool = False,
) -> HoldingAnalysis:
    if unavailable:
        return HoldingAnalysis(
            symbol=symbol, sector=sector, quantity=quantity, average_cost=average_cost,
            latest_price=None, market_value=None, weight=None, unrealized_pnl=None,
            unrealized_pnl_pct=None, report=None, error="insufficient data",
        )
    market_value = quantity * latest_price if latest_price is not None else None
    unrealized_pnl = (market_value - quantity * average_cost) if market_value is not None and average_cost is not None else None
    unrealized_pnl_pct = (
        (unrealized_pnl / (quantity * average_cost) * 100.0)
        if unrealized_pnl is not None and average_cost not in (None, 0) else None
    )
    return HoldingAnalysis(
        symbol=symbol, sector=sector, quantity=quantity, average_cost=average_cost,
        latest_price=latest_price, market_value=market_value, weight=weight,
        unrealized_pnl=unrealized_pnl, unrealized_pnl_pct=unrealized_pnl_pct,
        report=report or make_report(symbol=symbol, decision=decision),
    )


def make_holdings(specs: List[dict]) -> List[HoldingAnalysis]:
    return [make_holding_analysis(**spec) for spec in specs]
