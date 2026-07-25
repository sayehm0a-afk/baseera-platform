"""OutputFormatter: renders an `AnalystReport` into the shapes callers
need -- a plain dict (what the REST layer turns into JSON), Markdown
(for a rendered report view), or plain text (for logs, emails, or a
terminal). Pure presentation -- it reads `AnalystReport` fields and
formats them, computing nothing.
"""

from typing import List

from src.analysis.analyst.types import AnalystReport


def _bullet_list(items: List[str]) -> List[str]:
    return [f"- {item}" for item in items] if items else ["- None identified."]


class OutputFormatter:
    @staticmethod
    def to_dict(report: AnalystReport) -> dict:
        decision = report.decision
        explanation = report.explanation
        return {
            "symbol": report.symbol,
            "generated_at": report.generated_at.isoformat(),
            "engine_version": report.engine_version,
            "recommendation": decision.recommendation.value,
            "confidence": decision.confidence,
            "final_score": decision.final_score,
            "target_price": decision.target_price,
            "stop_loss": decision.stop_loss,
            "time_horizon": decision.time_horizon.value,
            "expected_return_pct": decision.expected_return_pct,
            "risk_level": decision.risk_level.value,
            "position_size": decision.position_size.value,
            "investment_summary": explanation.investment_summary,
            "technical_reasoning": explanation.technical_reasoning,
            "fundamental_reasoning": explanation.fundamental_reasoning,
            "risk_explanation": explanation.risk_explanation,
            "bullish_factors": list(explanation.bullish_factors),
            "bearish_factors": list(explanation.bearish_factors),
            "confidence_explanation": explanation.confidence_explanation,
            "target_price_explanation": explanation.target_price_explanation,
            "stop_loss_explanation": explanation.stop_loss_explanation,
            "time_horizon_explanation": explanation.time_horizon_explanation,
            "alternative_scenarios": list(explanation.alternative_scenarios),
            "final_recommendation_rationale": explanation.final_recommendation_rationale,
        }

    @staticmethod
    def to_markdown(report: AnalystReport) -> str:
        decision = report.decision
        explanation = report.explanation
        lines = [
            f"# Analyst Report: {report.symbol}",
            "",
            f"**Recommendation:** {decision.recommendation.value.replace('_', ' ').title()}  ",
            f"**Confidence:** {decision.confidence:.1f}%  ",
            f"**Final Score:** {decision.final_score:.1f}/100  ",
            f"**Target Price:** {decision.target_price if decision.target_price is not None else 'N/A'}  ",
            f"**Stop Loss:** {decision.stop_loss if decision.stop_loss is not None else 'N/A'}  ",
            f"**Time Horizon:** {decision.time_horizon.value.replace('_', ' ').title()}  ",
            f"**Risk Level:** {decision.risk_level.value.title()}  ",
            f"**Position Size:** {decision.position_size.value.title()}  ",
            "",
            "## Investment Summary",
            explanation.investment_summary,
            "",
            "## Technical Reasoning",
            explanation.technical_reasoning,
            "",
            "## Fundamental Reasoning",
            explanation.fundamental_reasoning,
            "",
            "## Risk Explanation",
            explanation.risk_explanation,
            "",
            "## Bullish Factors",
            *_bullet_list(explanation.bullish_factors),
            "",
            "## Bearish Factors",
            *_bullet_list(explanation.bearish_factors),
            "",
            "## Confidence Explanation",
            explanation.confidence_explanation,
            "",
            "## Target Price Explanation",
            explanation.target_price_explanation,
            "",
            "## Stop Loss Explanation",
            explanation.stop_loss_explanation,
            "",
            "## Time Horizon Explanation",
            explanation.time_horizon_explanation,
            "",
            "## Alternative Scenarios",
            *_bullet_list(explanation.alternative_scenarios),
            "",
            "## Final Recommendation Rationale",
            explanation.final_recommendation_rationale,
            "",
            f"*Generated at {report.generated_at.isoformat()} by AnalystEngine v{report.engine_version}.*",
        ]
        return "\n".join(lines)

    @staticmethod
    def to_text(report: AnalystReport) -> str:
        decision = report.decision
        explanation = report.explanation
        sections = [
            f"ANALYST REPORT: {report.symbol}",
            f"Recommendation: {decision.recommendation.value.replace('_', ' ').title()}",
            f"Confidence: {decision.confidence:.1f}%",
            f"Final Score: {decision.final_score:.1f}/100",
            "",
            "INVESTMENT SUMMARY",
            explanation.investment_summary,
            "",
            "TECHNICAL REASONING",
            explanation.technical_reasoning,
            "",
            "FUNDAMENTAL REASONING",
            explanation.fundamental_reasoning,
            "",
            "RISK EXPLANATION",
            explanation.risk_explanation,
            "",
            "BULLISH FACTORS",
            "\n".join(explanation.bullish_factors) or "None identified.",
            "",
            "BEARISH FACTORS",
            "\n".join(explanation.bearish_factors) or "None identified.",
            "",
            "CONFIDENCE EXPLANATION",
            explanation.confidence_explanation,
            "",
            "TARGET PRICE EXPLANATION",
            explanation.target_price_explanation,
            "",
            "STOP LOSS EXPLANATION",
            explanation.stop_loss_explanation,
            "",
            "TIME HORIZON EXPLANATION",
            explanation.time_horizon_explanation,
            "",
            "ALTERNATIVE SCENARIOS",
            "\n".join(explanation.alternative_scenarios) or "None identified.",
            "",
            "FINAL RECOMMENDATION RATIONALE",
            explanation.final_recommendation_rationale,
        ]
        return "\n".join(sections)
