"""Unit tests for AnalystEngine -- verifies it wires
AIDecisionEngine.decide() (unchanged, reused as a black box) into
ReasoningPipeline.run() without recomputing anything itself. Uses fake
decision_engine/pipeline doubles so this test is isolated from a real
AIDecisionEngine/ReasoningPipeline run (each already covered by their
own tests)."""

import pytest

from src.analysis.analyst.analyst_engine import ANALYST_ENGINE_VERSION, AnalystEngine
from src.analysis.analyst.types import Explanation
from src.analysis.recommendation.types import AnalysisContext
from tests.unit.analysis.analyst._fixtures import make_decision

_EXPLANATION = Explanation(
    investment_summary="summary", technical_reasoning="tech", fundamental_reasoning="fund",
    risk_explanation="risk", bullish_factors=["b1"], bearish_factors=["b2"],
    confidence_explanation="conf", target_price_explanation="target", stop_loss_explanation="stop",
    time_horizon_explanation="horizon", alternative_scenarios=["alt"], final_recommendation_rationale="final",
)


class _FakeDecisionEngine:
    def __init__(self, decision):
        self._decision = decision
        self.calls = []

    def decide(self, context, requesting_user_id=None):
        self.calls.append((context, requesting_user_id))
        return self._decision


class _FakePipeline:
    def __init__(self, explanation):
        self._explanation = explanation
        self.calls = []

    async def run(self, context, decision, requesting_user_id=None):
        self.calls.append((context, decision, requesting_user_id))
        return self._explanation


@pytest.mark.asyncio
async def test_analyze_reuses_the_decision_engines_output_verbatim():
    decision = make_decision(symbol="2222")
    decision_engine = _FakeDecisionEngine(decision)
    pipeline = _FakePipeline(_EXPLANATION)
    context = AnalysisContext(symbol="2222", latest_price=100.0)

    report = await AnalystEngine(decision_engine=decision_engine, pipeline=pipeline).analyze(context)

    assert report.symbol == "2222"
    assert report.decision is decision
    assert report.explanation is _EXPLANATION
    assert report.engine_version == ANALYST_ENGINE_VERSION
    assert decision_engine.calls == [(context, None)]
    assert pipeline.calls == [(context, decision, None)]


@pytest.mark.asyncio
async def test_default_construction_uses_real_ai_decision_engine_and_pipeline():
    context = AnalysisContext(symbol="2222", latest_price=100.0)
    report = await AnalystEngine().analyze(context)

    assert report.symbol == "2222"
    assert report.engine_version == ANALYST_ENGINE_VERSION
    assert report.decision.symbol == "2222"
    for field in (
        report.explanation.investment_summary, report.explanation.technical_reasoning,
        report.explanation.fundamental_reasoning, report.explanation.risk_explanation,
        report.explanation.confidence_explanation, report.explanation.target_price_explanation,
        report.explanation.stop_loss_explanation, report.explanation.time_horizon_explanation,
        report.explanation.final_recommendation_rationale,
    ):
        assert field
