"""PublicationGate: decides whether one symbol's already-computed
`SymbolScanOutcome` may be shown in a "this is a real opportunity"
ranking category (TOP_BUY, TOP_STRONG_BUY, TOP_LONG_TERM_INVESTMENT,
TOP_SWING_TRADE, NEW_OPPORTUNITIES) -- the missing step that let
symbol 1020 reach TOP_BUY #1 in the 2026-07-30 live scan purely by
having the highest `final_score`, with no check on whether the trade
it implied (buy at price, target above price, acceptable risk/reward)
actually made sense.

This module computes no new numbers. Every input it reads
(`target_price`, `stop_loss`, `expected_return_pct`,
`risk_reward_ratio`, `entry_quality`, `confidence`) already exists on
`InvestmentDecision` (src/analysis/decision/ai_decision_engine.py) --
this is a pure evaluation of evidence already produced, run at rank
time, not persisted (matching this whole layer's "computed on read"
convention, see ranking.py's own module docstring).

Two gates the wider mandate calls for -- sector-relative and
TASI/benchmark-relative evidence -- are recorded as `NOT_EVALUATED`
but deliberately never block publication: `AIDecisionEngine` does not
currently compute a sector-relative or benchmark-relative score at
all (no TASI integration exists yet, see docs/phase9_market_
intelligence/MARKET_INTELLIGENCE_REPORT.md), so there is no claim
being made that evidence could contradict. Blocking on the absence of
an input nothing downstream ever uses would just make every
recommendation NOT_EVALUATED for a reason unrelated to its actual
quality. What *is* enforced structurally: nothing in this module or
downstream ever manufactures a sector- or benchmark-relative claim
from these NOT_EVALUATED gates -- see PublicationEvaluation.disclosures.
"""

from typing import List

from src.analysis.decision.types import EntryQuality
from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.config import get_min_risk_reward_ratio
from src.market_intelligence.types import (
    GateResult,
    GateStatus,
    PublicationEvaluation,
    PublicationStatus,
    SymbolScanOutcome,
)

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}
_SELL_LIKE = {Recommendation.SELL, Recommendation.STRONG_SELL}


def evaluate_publication(outcome: SymbolScanOutcome) -> PublicationEvaluation:
    if not outcome.success or outcome.report is None:
        return PublicationEvaluation(
            status=PublicationStatus.INSUFFICIENT_DATA,
            gates=[GateResult(
                name="data_availability", status=GateStatus.FAIL,
                detail=outcome.skipped_reason or outcome.error or "no analyst report produced",
            )],
            disclosures=[],
        )

    gates: List[GateResult] = [GateResult(name="data_availability", status=GateStatus.PASS, detail="analyst report present")]
    disclosures: List[str] = []

    gates.append(_price_validity_gate(outcome))
    gates.append(_confidence_gate(outcome))
    gates.append(_targets_gate(outcome))
    gates.append(_sector_data_gate(outcome, disclosures))
    gates.append(_benchmark_data_gate(disclosures))

    critical_fail = next((g for g in gates if g.status is GateStatus.FAIL), None)
    if critical_fail is not None:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    recommendation = outcome.recommendation
    is_actionable = recommendation in _BUY_LIKE or recommendation in _SELL_LIKE

    if not is_actionable:
        gates.append(GateResult(name="risk_reward", status=GateStatus.NOT_EVALUATED, detail="HOLD proposes no trade"))
        gates.append(GateResult(name="entry_quality", status=GateStatus.NOT_EVALUATED, detail="HOLD proposes no trade"))
        return PublicationEvaluation(status=PublicationStatus.PUBLISHED, gates=gates, disclosures=disclosures)

    risk_reward_gate = _risk_reward_gate(outcome, recommendation)
    gates.append(risk_reward_gate)
    if risk_reward_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    entry_quality = outcome.report.decision.entry_quality
    entry_quality_gate = GateResult(
        name="entry_quality",
        status=GateStatus.FAIL if entry_quality is EntryQuality.POOR else GateStatus.PASS,
        detail=f"entry quality: {entry_quality.value}",
    )
    gates.append(entry_quality_gate)
    if entry_quality_gate.status is GateStatus.FAIL:
        # A poor entry does not invalidate the underlying thesis the way a
        # missing critical input or a bad risk/reward does -- downgraded to
        # WATCH_ONLY (adversarial case #12: "strong fundamentals but no
        # entry setup -> watchlist, not immediate BUY"), not rejected outright.
        return PublicationEvaluation(status=PublicationStatus.WATCH_ONLY, gates=gates, disclosures=disclosures)

    return PublicationEvaluation(status=PublicationStatus.PUBLISHED, gates=gates, disclosures=disclosures)


def _price_validity_gate(outcome: SymbolScanOutcome) -> GateResult:
    if outcome.latest_price is not None and outcome.latest_price > 0:
        return GateResult(name="price_validity", status=GateStatus.PASS, detail=f"price={outcome.latest_price}")
    return GateResult(name="price_validity", status=GateStatus.FAIL, detail="no valid latest price")


def _confidence_gate(outcome: SymbolScanOutcome) -> GateResult:
    if outcome.confidence is not None:
        return GateResult(name="confidence_present", status=GateStatus.PASS, detail=f"confidence={outcome.confidence}")
    return GateResult(name="confidence_present", status=GateStatus.FAIL, detail="no confidence computed")


def _targets_gate(outcome: SymbolScanOutcome) -> GateResult:
    decision = outcome.report.decision
    if decision.target_price is not None and decision.stop_loss is not None and decision.expected_return_pct is not None:
        return GateResult(name="targets_present", status=GateStatus.PASS, detail="target/stop/expected-return computed")
    return GateResult(name="targets_present", status=GateStatus.FAIL, detail="target price or stop loss unavailable")


def _risk_reward_gate(outcome: SymbolScanOutcome, recommendation: Recommendation) -> GateResult:
    decision = outcome.report.decision
    expected_return_pct = decision.expected_return_pct
    risk_reward_ratio = decision.risk_reward_ratio

    if recommendation in _BUY_LIKE and expected_return_pct is not None and expected_return_pct <= 0:
        return GateResult(
            name="risk_reward", status=GateStatus.FAIL,
            detail=f"BUY with non-positive expected return ({expected_return_pct}%) -- target does not sit above entry",
        )
    if recommendation in _SELL_LIKE and expected_return_pct is not None and expected_return_pct >= 0:
        return GateResult(
            name="risk_reward", status=GateStatus.FAIL,
            detail=f"SELL with non-negative expected return ({expected_return_pct}%) -- target does not sit below entry",
        )

    min_ratio = get_min_risk_reward_ratio()
    if risk_reward_ratio is None:
        return GateResult(name="risk_reward", status=GateStatus.NOT_EVALUATED, detail="no stop distance to compute risk/reward")
    if risk_reward_ratio < min_ratio:
        return GateResult(
            name="risk_reward", status=GateStatus.FAIL,
            detail=f"risk/reward {risk_reward_ratio:.2f} below minimum {min_ratio:.2f}",
        )
    return GateResult(name="risk_reward", status=GateStatus.PASS, detail=f"risk/reward {risk_reward_ratio:.2f}")


def _sector_data_gate(outcome: SymbolScanOutcome, disclosures: List[str]) -> GateResult:
    if outcome.sector:
        return GateResult(name="sector_data", status=GateStatus.PASS, detail=outcome.sector)
    disclosures.append("no sector classification available for this symbol -- no sector-relative claim is made")
    return GateResult(name="sector_data", status=GateStatus.NOT_EVALUATED, detail="sector unknown")


def _benchmark_data_gate(disclosures: List[str]) -> GateResult:
    disclosures.append("TASI/benchmark integration does not exist yet -- no market-relative claim is made")
    return GateResult(name="benchmark_data", status=GateStatus.NOT_EVALUATED, detail="TASI not integrated")


def is_publishable(outcome: SymbolScanOutcome) -> bool:
    return evaluate_publication(outcome).status is PublicationStatus.PUBLISHED
