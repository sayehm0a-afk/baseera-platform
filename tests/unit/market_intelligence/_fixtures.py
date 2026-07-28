"""Small builder helpers shared by the Autonomous Market Intelligence
Layer unit tests -- the same "hand-built fake data, not a real engine
run" technique tests/unit/analysis/analyst/_fixtures.py already uses,
applied one layer up so each market_intelligence module can be tested
in isolation from a real scan.
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
from src.analysis.recommendation.types import AnalysisContext, Recommendation
from src.market_intelligence.types import SymbolScanOutcome


def make_breakdown(category="Technical Analysis", points=15.0, available=True) -> DecisionFactorBreakdown:
    return DecisionFactorBreakdown(category=category, points=points, weight=0.25, confidence=90.0, available=available)


def make_decision(
    symbol="2222",
    recommendation=Recommendation.BUY,
    confidence=70.0,
    final_score=65.0,
    target_price: Optional[float] = 105.0,
    stop_loss: Optional[float] = 97.0,
    time_horizon=TimeHorizon.MEDIUM_TERM,
    expected_return_pct: Optional[float] = 5.0,
    risk_level=RiskLevel.MEDIUM,
    position_size=PositionSize.STANDARD,
    breakdown: Optional[List[DecisionFactorBreakdown]] = None,
) -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol, recommendation=recommendation, confidence=confidence, final_score=final_score,
        target_price=target_price, stop_loss=stop_loss, time_horizon=time_horizon,
        expected_return_pct=expected_return_pct, risk_level=risk_level, position_size=position_size,
        reasons=[f"{recommendation.value} on {symbol}."],
        breakdown=breakdown if breakdown is not None else [make_breakdown()],
        signals=[], generated_at=datetime.now(timezone.utc),
    )


def make_report(symbol="2222", decision: Optional[InvestmentDecision] = None) -> AnalystReport:
    decision = decision or make_decision(symbol=symbol)
    explanation = Explanation(
        investment_summary="summary", technical_reasoning="tech", fundamental_reasoning="fund",
        risk_explanation="risk", bullish_factors=["Bullish factor."], bearish_factors=["Bearish factor."],
        confidence_explanation="conf", target_price_explanation="target", stop_loss_explanation="stop",
        time_horizon_explanation="horizon", alternative_scenarios=[], final_recommendation_rationale="final",
    )
    return AnalystReport(
        symbol=symbol, decision=decision, explanation=explanation,
        generated_at=datetime.now(timezone.utc), engine_version="1.0.0",
    )


def make_outcome(
    symbol="2222",
    sector: Optional[str] = "Energy",
    success=True,
    report: Optional[AnalystReport] = None,
    skipped_reason: Optional[str] = None,
    error: Optional[str] = None,
    latest_price: Optional[float] = 100.0,
    technical_snapshot: Optional[dict] = None,
    fundamental_snapshot: Optional[dict] = None,
    decision: Optional[InvestmentDecision] = None,
    context: Optional[AnalysisContext] = None,
) -> SymbolScanOutcome:
    if success and report is None:
        report = make_report(symbol=symbol, decision=decision)
    return SymbolScanOutcome(
        symbol=symbol, sector=sector, success=success, report=report,
        skipped_reason=skipped_reason, error=error, latest_price=latest_price,
        technical_snapshot=technical_snapshot, fundamental_snapshot=fundamental_snapshot,
        context=context,
    )
