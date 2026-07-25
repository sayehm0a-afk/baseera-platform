"""Unit tests for ReasoningPipeline -- orchestration only. Real
sub-stages are used (they're each already covered by their own unit
tests) so these tests focus on wiring: that every section ends up
populated, and that the optional LLMAdapter extension point is only
consulted for the three eligible sections."""

import pytest

from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationResult, NullLLMAdapter
from src.analysis.analyst.reasoning_pipeline import ReasoningPipeline
from src.analysis.recommendation.types import AnalysisContext
from tests.unit.analysis.analyst._fixtures import make_decision


class _EmptyResultAdapter(LLMAdapter):
    """Returns an empty completion -- proves the pipeline falls back to
    the deterministic baseline rather than blanking a section out."""

    name = "empty"

    async def generate(self, request):
        return LLMGenerationResult(text="", model="empty-adapter")


@pytest.mark.asyncio
async def test_run_without_an_adapter_produces_a_fully_populated_explanation():
    decision = make_decision()
    context = AnalysisContext(symbol="2222", latest_price=100.0)

    explanation = await ReasoningPipeline().run(context, decision)

    assert explanation.investment_summary
    assert explanation.technical_reasoning
    assert explanation.fundamental_reasoning
    assert explanation.risk_explanation
    assert explanation.confidence_explanation
    assert explanation.target_price_explanation
    assert explanation.stop_loss_explanation
    assert explanation.time_horizon_explanation
    assert explanation.final_recommendation_rationale
    assert isinstance(explanation.bullish_factors, list)
    assert isinstance(explanation.bearish_factors, list)
    assert isinstance(explanation.alternative_scenarios, list)


@pytest.mark.asyncio
async def test_llm_adapter_is_used_for_the_three_eligible_sections_only():
    decision = make_decision()
    context = AnalysisContext(symbol="2222", latest_price=100.0)

    pipeline = ReasoningPipeline(llm_adapter=NullLLMAdapter())
    explanation = await pipeline.run(context, decision)

    # NullLLMAdapter echoes its prompt back, which is grounded in the
    # baseline text wrapped in an LLM instruction -- so the eligible
    # sections should now contain that instruction text.
    assert "professional equity analyst" in explanation.technical_reasoning
    assert "professional equity analyst" in explanation.fundamental_reasoning
    assert "professional equity analyst" in explanation.risk_explanation

    # These sections are never offered to the adapter.
    assert "professional equity analyst" not in explanation.target_price_explanation
    assert "professional equity analyst" not in explanation.stop_loss_explanation
    assert "professional equity analyst" not in explanation.time_horizon_explanation
    assert "professional equity analyst" not in explanation.investment_summary
    assert "professional equity analyst" not in explanation.final_recommendation_rationale


@pytest.mark.asyncio
async def test_falls_back_to_baseline_when_adapter_returns_empty_text():
    decision = make_decision()
    context = AnalysisContext(symbol="2222", latest_price=100.0)

    pipeline = ReasoningPipeline(llm_adapter=_EmptyResultAdapter())
    explanation = await pipeline.run(context, decision)

    # The deterministic fallback (never blank) is what should end up in the section.
    assert explanation.technical_reasoning
    assert "professional equity analyst" not in explanation.technical_reasoning
