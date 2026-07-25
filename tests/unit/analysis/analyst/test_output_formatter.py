"""Unit tests for OutputFormatter -- pure presentation over an
AnalystReport, computing nothing."""

from datetime import datetime, timezone

from src.analysis.analyst.output_formatter import OutputFormatter
from src.analysis.analyst.types import AnalystReport, Explanation
from tests.unit.analysis.analyst._fixtures import make_decision


def _report(bullish=None, bearish=None, alternative_scenarios=None):
    decision = make_decision()
    explanation = Explanation(
        investment_summary="Summary text.",
        technical_reasoning="Technical text.",
        fundamental_reasoning="Fundamental text.",
        risk_explanation="Risk text.",
        bullish_factors=bullish if bullish is not None else ["Factor A"],
        bearish_factors=bearish if bearish is not None else ["Factor B"],
        confidence_explanation="Confidence text.",
        target_price_explanation="Target text.",
        stop_loss_explanation="Stop text.",
        time_horizon_explanation="Horizon text.",
        alternative_scenarios=alternative_scenarios if alternative_scenarios is not None else ["Scenario A"],
        final_recommendation_rationale="Final rationale text.",
    )
    return AnalystReport(
        symbol="2222",
        decision=decision,
        explanation=explanation,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        engine_version="1.0.0",
    )


def test_to_dict_includes_every_explanation_and_decision_field():
    report = _report()
    body = OutputFormatter.to_dict(report)

    assert body["symbol"] == "2222"
    assert body["engine_version"] == "1.0.0"
    assert body["recommendation"] == report.decision.recommendation.value
    assert body["investment_summary"] == "Summary text."
    assert body["bullish_factors"] == ["Factor A"]
    assert body["bearish_factors"] == ["Factor B"]
    assert body["alternative_scenarios"] == ["Scenario A"]
    assert body["generated_at"] == "2026-01-01T00:00:00+00:00"


def test_to_markdown_includes_every_section_heading():
    report = _report()
    markdown = OutputFormatter.to_markdown(report)

    assert markdown.startswith("# Analyst Report: 2222")
    for heading in (
        "## Investment Summary", "## Technical Reasoning", "## Fundamental Reasoning", "## Risk Explanation",
        "## Bullish Factors", "## Bearish Factors", "## Confidence Explanation", "## Target Price Explanation",
        "## Stop Loss Explanation", "## Time Horizon Explanation", "## Alternative Scenarios",
        "## Final Recommendation Rationale",
    ):
        assert heading in markdown
    assert "- Factor A" in markdown
    assert "- Factor B" in markdown


def test_to_markdown_shows_fallback_when_no_bullish_factors():
    report = _report(bullish=[])
    markdown = OutputFormatter.to_markdown(report)
    assert "- None identified." in markdown


def test_to_markdown_shows_fallback_when_no_alternative_scenarios():
    report = _report(alternative_scenarios=[])
    markdown = OutputFormatter.to_markdown(report)
    assert "- None identified." in markdown


def test_to_text_includes_every_section_and_fallback_for_empty_lists():
    report = _report(bearish=[])
    text = OutputFormatter.to_text(report)

    assert "ANALYST REPORT: 2222" in text
    assert "TECHNICAL REASONING" in text
    assert "Factor A" in text
    assert "None identified." in text
