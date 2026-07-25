"""read_model: reconstructs a `SymbolScanOutcome`-compatible object
from a persisted `SymbolIntelligenceRecord` row, so REST GET routes
that read historical scan data can reuse `RankingEngine`/
`WatchlistEngine`/`SectorAnalyzer`/`MarketSnapshotBuilder` exactly as
`scan_job_runner` does, rather than re-implementing their filter/sort/
aggregate rules a second time at the API layer -- the same "no
duplicate business logic" reasoning applied to reads, not just writes.

Only the decision-level fields every one of those engines actually
reads are reconstructed faithfully (recommendation, confidence,
final_score, target price/stop loss/expected return, risk level, time
horizon, position size, technical/fundamental score via a 2-entry
breakdown, RSI/ADX/Bollinger-upper, dividend yield, and the persisted
bullish/bearish factor text). `Explanation`'s prose fields -- never
read by any ranking/watchlist/sector/snapshot rule -- are left as
empty strings; a caller that needs the full report narrative should
call `GET /analyst-report/{symbol}` instead, which always re-runs
`AnalystEngine` live rather than reading a persisted summary.
"""

from src.analysis.analyst.types import AnalystReport, Explanation
from src.analysis.decision.ai_decision_engine import CATEGORY_LABELS
from src.analysis.decision.types import (
    DecisionFactorBreakdown,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.recommendation.types import Recommendation
from src.domain.models import SymbolIntelligenceRecord
from src.market_intelligence.types import SymbolScanOutcome


def _breakdown(record: SymbolIntelligenceRecord) -> list:
    entries = []
    if record.technical_score is not None:
        entries.append(
            DecisionFactorBreakdown(
                category=CATEGORY_LABELS["technical"], points=float(record.technical_score) - 50.0,
                weight=0.0, confidence=0.0, available=True,
            )
        )
    if record.fundamental_score is not None:
        entries.append(
            DecisionFactorBreakdown(
                category=CATEGORY_LABELS["fundamental"], points=float(record.fundamental_score) - 50.0,
                weight=0.0, confidence=0.0, available=True,
            )
        )
    return entries


def _technical_snapshot(record: SymbolIntelligenceRecord):
    snapshot = {}
    if record.rsi is not None:
        snapshot["rsi_14"] = float(record.rsi)
    if record.adx is not None:
        snapshot["adx_14"] = float(record.adx)
    if record.bollinger_upper is not None:
        snapshot["bollinger"] = {"upper": float(record.bollinger_upper)}
    return snapshot or None


def _fundamental_snapshot(record: SymbolIntelligenceRecord):
    return {"dividend_yield": float(record.dividend_yield)} if record.dividend_yield is not None else None


def outcome_from_record(record: SymbolIntelligenceRecord) -> SymbolScanOutcome:
    decision = InvestmentDecision(
        symbol=record.symbol,
        recommendation=Recommendation(record.recommendation.value),
        confidence=float(record.confidence),
        final_score=float(record.final_score),
        target_price=float(record.target_price) if record.target_price is not None else None,
        stop_loss=float(record.stop_loss) if record.stop_loss is not None else None,
        time_horizon=TimeHorizon(record.time_horizon) if record.time_horizon else TimeHorizon.SHORT_TERM,
        expected_return_pct=float(record.expected_return_pct) if record.expected_return_pct is not None else None,
        risk_level=RiskLevel(record.risk_level) if record.risk_level else RiskLevel.MEDIUM,
        position_size=PositionSize(record.position_size) if record.position_size else PositionSize.NONE,
        reasons=[],
        breakdown=_breakdown(record),
        signals=[],
        generated_at=record.evaluated_at,
    )
    explanation = Explanation(
        investment_summary="", technical_reasoning="", fundamental_reasoning="", risk_explanation="",
        bullish_factors=list(record.bullish_factors or []), bearish_factors=list(record.bearish_factors or []),
        confidence_explanation="", target_price_explanation="", stop_loss_explanation="",
        time_horizon_explanation="", alternative_scenarios=[], final_recommendation_rationale="",
    )
    report = AnalystReport(
        symbol=record.symbol, decision=decision, explanation=explanation,
        generated_at=record.evaluated_at, engine_version=record.engine_version,
    )
    return SymbolScanOutcome(
        symbol=record.symbol,
        sector=record.sector,
        success=True,
        report=report,
        latest_price=float(record.latest_price) if record.latest_price is not None else None,
        technical_snapshot=_technical_snapshot(record),
        fundamental_snapshot=_fundamental_snapshot(record),
        scanned_at=record.evaluated_at,
    )
