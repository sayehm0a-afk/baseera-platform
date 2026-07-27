"""Unit tests for PromptTemplateManager."""

from src.analysis.analyst.prompt_templates import PromptTemplateManager
from src.analysis.analyst.types import FactorStrength, InterpretedFactor
from src.analysis.recommendation.types import SignalDirection


def _factor(description, impact=10.0):
    return InterpretedFactor(
        category="Technical Analysis",
        description=description,
        direction=SignalDirection.BULLISH,
        strength=FactorStrength.MODERATE,
        impact=impact,
    )


def test_render_fills_a_named_template():
    manager = PromptTemplateManager()
    text = manager.render(
        "technical_reasoning",
        symbol="2222",
        tilt="bullish",
        factor_clause="Momentum is strong.",
        indicator_summary="RSI at 60",
    )
    assert "2222" in text
    assert "bullish" in text
    assert "RSI at 60" in text


def test_build_prompt_grounds_the_instruction_in_the_baseline_text():
    manager = PromptTemplateManager()
    prompt = manager.build_prompt("technical_reasoning", baseline_text="Technical analysis for 2222 is bullish.")
    assert "Technical analysis for 2222 is bullish." in prompt
    assert "Do not invent" in prompt


def test_build_prompt_falls_back_to_a_generic_instruction_for_unknown_sections():
    manager = PromptTemplateManager()
    prompt = manager.build_prompt("some_unknown_section", baseline_text="baseline text")
    assert "baseline text" in prompt


def test_join_factors_empty_list_returns_empty_string():
    manager = PromptTemplateManager()
    assert manager.join_factors([]) == ""


def test_join_factors_single_factor():
    manager = PromptTemplateManager()
    clause = manager.join_factors([_factor("RSI is bullish.")])
    assert clause == "This is supported by rSI is bullish."


def test_join_factors_two_factors_joined_with_and():
    manager = PromptTemplateManager()
    clause = manager.join_factors([_factor("Momentum is bullish."), _factor("ADX confirms trend.")])
    # Only the very first character of the whole joined clause is
    # lowercased (to read naturally after "supported by"), not each
    # factor individually.
    assert clause == "This is supported by momentum is bullish and ADX confirms trend."


def test_join_factors_respects_max_factors():
    manager = PromptTemplateManager()
    factors = [_factor(f"Factor {i}.") for i in range(5)]
    clause = manager.join_factors(factors, max_factors=2)
    assert "Factor 1" in clause
    assert "Factor 2" not in clause
