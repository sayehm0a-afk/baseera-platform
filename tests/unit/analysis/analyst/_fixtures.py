"""Small builder helpers shared by the Autonomous AI Analyst Framework
unit tests -- the same "hand-built fake data, not a real engine run"
technique test_ai_decision_engine.py already uses, applied one layer
up so each analyst module can be tested in complete isolation from a
real TechnicalAnalysisEngine/FundamentalAnalysisEngine/AIDecisionEngine
run.
"""

from datetime import datetime, timezone
from typing import List, Optional

from src.analysis.analyst.types import Evidence
from src.analysis.decision.types import (
    DecisionFactorBreakdown,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.recommendation.types import Recommendation, Signal, SignalDirection


def make_signal(
    name="rsi_bullish",
    description="RSI(14)=60 is above 50, indicating bullish momentum.",
    direction=SignalDirection.BULLISH,
    source="technical",
    impact=12.0,
) -> Signal:
    return Signal(name=name, description=description, direction=direction, source=source, impact=impact)


def make_breakdown(
    category="Technical Analysis", points=15.0, weight=0.25, confidence=90.0, available=True, notes=None
) -> DecisionFactorBreakdown:
    return DecisionFactorBreakdown(
        category=category, points=points, weight=weight, confidence=confidence, available=available, notes=notes
    )


def make_decision(
    symbol="2222",
    recommendation=Recommendation.BUY,
    confidence=75.0,
    final_score=65.0,
    target_price: Optional[float] = 105.0,
    stop_loss: Optional[float] = 97.0,
    time_horizon=TimeHorizon.MEDIUM_TERM,
    expected_return_pct: Optional[float] = 5.0,
    risk_level=RiskLevel.MEDIUM,
    position_size=PositionSize.STANDARD,
    reasons: Optional[List[str]] = None,
    breakdown: Optional[List[DecisionFactorBreakdown]] = None,
    signals: Optional[List[Signal]] = None,
) -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol,
        recommendation=recommendation,
        confidence=confidence,
        final_score=final_score,
        target_price=target_price,
        stop_loss=stop_loss,
        time_horizon=time_horizon,
        expected_return_pct=expected_return_pct,
        risk_level=risk_level,
        position_size=position_size,
        reasons=reasons or [f"Buy on {symbol}."],
        breakdown=breakdown if breakdown is not None else [make_breakdown()],
        signals=signals if signals is not None else [make_signal()],
        generated_at=datetime.now(timezone.utc),
    )


def make_evidence(
    symbol="2222",
    decision: Optional[InvestmentDecision] = None,
    technical_result=None,
    fundamental_result=None,
    signals: Optional[List[Signal]] = None,
    contributor_breakdown: Optional[List[DecisionFactorBreakdown]] = None,
) -> Evidence:
    decision = decision or make_decision(symbol=symbol)
    return Evidence(
        symbol=symbol,
        decision=decision,
        technical_result=technical_result,
        fundamental_result=fundamental_result,
        signals=signals if signals is not None else decision.signals,
        contributor_breakdown=contributor_breakdown if contributor_breakdown is not None else decision.breakdown,
    )
