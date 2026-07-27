"""Unit tests for EvidenceCollector -- pure reorganization, zero
recomputation."""

from src.analysis.analyst.evidence_collector import EvidenceCollector
from src.analysis.recommendation.types import AnalysisContext
from tests.unit.analysis.analyst._fixtures import make_decision


def test_collect_carries_context_and_decision_fields_through_unchanged():
    decision = make_decision(symbol="2222")
    context = AnalysisContext(symbol="2222", technical_result="tech-sentinel", fundamental_result="fund-sentinel")

    evidence = EvidenceCollector().collect(context, decision)

    assert evidence.symbol == "2222"
    assert evidence.decision is decision
    assert evidence.technical_result == "tech-sentinel"
    assert evidence.fundamental_result == "fund-sentinel"
    assert evidence.signals == decision.signals
    assert evidence.contributor_breakdown == decision.breakdown


def test_collect_leaves_technical_and_fundamental_none_when_context_has_none():
    decision = make_decision(symbol="2222")
    context = AnalysisContext(symbol="2222")

    evidence = EvidenceCollector().collect(context, decision)

    assert evidence.technical_result is None
    assert evidence.fundamental_result is None
