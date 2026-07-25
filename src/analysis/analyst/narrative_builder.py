"""NarrativeBuilder: turns `Evidence`/`InterpretedSignals` into the
prose sections of an `Explanation`.

Fully synchronous and deterministic -- every sentence is built from a
`PromptTemplateManager` template plus values read directly from
`Evidence` (indicator/ratio readings, `InvestmentDecision` fields), so
the same inputs always produce the same output, and every claim traces
back to a real, cited number. `ReasoningPipeline` is the only caller
that may additionally hand a section's baseline text to an
`LLMAdapter` for rephrasing -- this class itself never calls one.
"""

from typing import Any, List, Optional

from src.analysis.analyst.prompt_templates import PromptTemplateManager
from src.analysis.analyst.types import Evidence, InterpretedFactor, InterpretedSignals
from src.analysis.decision.types import TimeHorizon

_TECHNICAL_CATEGORIES = {"Technical Analysis", "Momentum", "Volume"}
_FUNDAMENTAL_CATEGORIES = {"Fundamental Analysis", "News", "Macro", "Insider Transactions", "Sector Rotation"}
_RISK_CATEGORIES = {"Risk"}

_TIME_HORIZON_LABELS = {
    TimeHorizon.SHORT_TERM: "short-term (days to a few weeks)",
    TimeHorizon.MEDIUM_TERM: "medium-term (weeks to a few months)",
    TimeHorizon.LONG_TERM: "long-term (months and beyond)",
}


def _indicator_latest(technical_result, name: str) -> Optional[Any]:
    if technical_result is None:
        return None
    output = technical_result.indicators.get(name)
    return output.latest() if output is not None else None


def _factors_in(factors: List[InterpretedFactor], categories: set) -> List[InterpretedFactor]:
    return [f for f in factors if f.category in categories]


def _format_number(value: Any) -> Optional[str]:
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return None


class NarrativeBuilder:
    def __init__(self, template_manager: Optional[PromptTemplateManager] = None):
        self._templates = template_manager or PromptTemplateManager()

    def build_technical_reasoning(self, evidence: Evidence, interpreted: InterpretedSignals) -> str:
        if not evidence.technical_available:
            return self._templates.render("technical_unavailable", symbol=evidence.symbol)

        relevant = _factors_in(interpreted.bullish_factors + interpreted.bearish_factors, _TECHNICAL_CATEGORIES)
        factor_clause = self._templates.join_factors(relevant)
        tilt = interpreted.category_tilts.get("Technical Analysis", "neutral")

        readings = []
        rsi = _format_number(_indicator_latest(evidence.technical_result, "rsi_14"))
        if rsi is not None:
            readings.append(f"RSI(14) at {rsi}")
        adx = _format_number(_indicator_latest(evidence.technical_result, "adx_14"))
        if adx is not None:
            readings.append(f"ADX(14) at {adx}")
        macd_latest = _indicator_latest(evidence.technical_result, "macd")
        if isinstance(macd_latest, dict):
            histogram = _format_number(macd_latest.get("histogram"))
            if histogram is not None:
                readings.append(f"MACD histogram at {histogram}")
        indicator_summary = ", ".join(readings) if readings else "no indicator readings were available"

        return self._templates.render(
            "technical_reasoning",
            symbol=evidence.symbol,
            tilt=tilt,
            factor_clause=factor_clause,
            indicator_summary=indicator_summary,
        )

    def build_fundamental_reasoning(self, evidence: Evidence, interpreted: InterpretedSignals) -> str:
        if not evidence.fundamental_available:
            return self._templates.render("fundamental_unavailable", symbol=evidence.symbol)

        relevant = _factors_in(interpreted.bullish_factors + interpreted.bearish_factors, _FUNDAMENTAL_CATEGORIES)
        factor_clause = self._templates.join_factors(relevant)
        tilt = interpreted.category_tilts.get("Fundamental Analysis", "neutral")

        readings = []
        for label, key in (("ROE", "return_on_equity"), ("net margin", "net_profit_margin"), ("P/E", "price_to_earnings")):
            output = evidence.fundamental_result.ratios.get(key)
            value = _format_number(output.value) if output is not None else None
            if value is not None:
                readings.append(f"{label} at {value}")
        ratio_summary = ", ".join(readings) if readings else "no ratio readings were available"

        return self._templates.render(
            "fundamental_reasoning",
            symbol=evidence.symbol,
            tilt=tilt,
            factor_clause=factor_clause,
            ratio_summary=ratio_summary,
        )

    def build_risk_explanation(self, evidence: Evidence, interpreted: InterpretedSignals) -> str:
        relevant = _factors_in(interpreted.bullish_factors + interpreted.bearish_factors, _RISK_CATEGORIES)
        factor_clause = self._templates.join_factors(relevant)
        return self._templates.render(
            "risk_explanation",
            risk_level=evidence.decision.risk_level.value.title(),
            position_size=evidence.decision.position_size.value.title(),
            factor_clause=factor_clause,
        )

    def build_target_price_explanation(self, evidence: Evidence) -> str:
        decision = evidence.decision
        reference_price = _reference_price(evidence)
        if decision.target_price is None or decision.expected_return_pct is None or reference_price is None:
            return self._templates.render("target_price_unavailable", symbol=evidence.symbol)
        return self._templates.render(
            "target_price_explanation",
            target_price=decision.target_price,
            expected_return_pct=decision.expected_return_pct,
            reference_price=reference_price,
        )

    def build_stop_loss_explanation(self, evidence: Evidence) -> str:
        decision = evidence.decision
        reference_price = _reference_price(evidence)
        if decision.stop_loss is None or reference_price is None:
            return self._templates.render("stop_loss_unavailable", symbol=evidence.symbol)
        return self._templates.render(
            "stop_loss_explanation",
            stop_loss=decision.stop_loss,
            reference_price=reference_price,
        )

    def build_time_horizon_explanation(self, evidence: Evidence) -> str:
        decision = evidence.decision
        label = _TIME_HORIZON_LABELS[decision.time_horizon]
        adx = _format_number(_indicator_latest(evidence.technical_result, "adx_14"))
        adx_clause = f", including trend strength (ADX at {adx})" if adx is not None else ""
        return self._templates.render("time_horizon_explanation", time_horizon=label, adx_clause=adx_clause)


def _reference_price(evidence: Evidence) -> Optional[float]:
    """The price target/stop loss were both computed against -- not
    stored on `InvestmentDecision` itself, so it is reconstructed the
    same way `AIDecisionEngine._compute_price_targets` derived it:
    target/stop distance from the price, back out the price from
    `expected_return_pct` when possible, else fall back to the
    technical engine's own latest Bollinger midpoint."""
    decision = evidence.decision
    if decision.target_price is not None and decision.expected_return_pct is not None:
        denominator = 1 + decision.expected_return_pct / 100.0
        if denominator != 0:
            return decision.target_price / denominator
    bollinger_latest = _indicator_latest(evidence.technical_result, "bollinger")
    if isinstance(bollinger_latest, dict):
        return bollinger_latest.get("middle")
    return None
