"""PromptTemplateManager: the Autonomous AI Analyst Framework's single
source of narrative wording.

Two distinct jobs live here, deliberately kept in one place so the
wording of a section never drifts between its deterministic and
LLM-enriched forms:

- `render()` fills a named Python format-string template with keyword
  arguments and returns the finished prose `NarrativeBuilder` /
  `RecommendationComposer` use as their (always computed) baseline
  text -- this is what every `Explanation` field contains today, since
  no `LLMAdapter` is wired into production.
- `build_prompt()` turns the same inputs into an LLM-oriented
  instruction string, grounded in that baseline text. It exists purely
  as the shape a future `LLMAdapter` call would consume -- see
  `reasoning_pipeline.py` for the one place it is actually invoked,
  and only when a caller explicitly injects an adapter.

`join_factors()` is a small shared helper for turning a list of
`InterpretedFactor`s into one flowing prose clause, used by both jobs.
"""

from typing import List

from src.analysis.analyst.types import InterpretedFactor

_TEMPLATES = {
    "technical_reasoning": (
        "Technical analysis for {symbol} is {tilt}. {factor_clause} "
        "Key indicator readings: {indicator_summary}."
    ),
    "technical_unavailable": (
        "Technical analysis for {symbol} could not be produced -- there is not enough ingested "
        "price history to compute the required indicators, so this reasoning relies solely on "
        "whatever fundamental and other evidence was available."
    ),
    "fundamental_reasoning": (
        "Fundamental analysis for {symbol} is {tilt}. {factor_clause} "
        "Key financial metrics: {ratio_summary}."
    ),
    "fundamental_unavailable": (
        "Fundamental analysis for {symbol} could not be produced -- no ingested financial "
        "statements are available for this symbol, so this reasoning relies solely on whatever "
        "technical and other evidence was available."
    ),
    "risk_explanation": (
        "Risk is assessed as {risk_level} and the position is sized as {position_size} for a new "
        "entry. {factor_clause}"
    ),
    "target_price_explanation": (
        "A target price of {target_price:.2f} implies an expected return of "
        "{expected_return_pct:.2f}% from the reference price of {reference_price:.2f}, derived from "
        "the decision's overall conviction and the symbol's recent average true range."
    ),
    "target_price_unavailable": (
        "A target price could not be computed for {symbol} -- no live or recent price was "
        "available to anchor the calculation."
    ),
    "stop_loss_explanation": (
        "A stop loss of {stop_loss:.2f} caps downside risk relative to the reference price of "
        "{reference_price:.2f}, sized from the symbol's recent average true range so it reflects "
        "this symbol's own volatility rather than a fixed percentage."
    ),
    "stop_loss_unavailable": (
        "A stop loss could not be computed for {symbol} -- no live or recent price was available "
        "to anchor the calculation."
    ),
    "time_horizon_explanation": (
        "This recommendation is framed as a {time_horizon} view, reflecting how strong the "
        "overall conviction is{adx_clause}."
    ),
    "investment_summary": (
        "{symbol} is rated {recommendation} with {confidence:.1f}% confidence (final score "
        "{final_score:.1f}/100). {conflict_clause}"
    ),
    "final_rationale": (
        "The {recommendation} rating on {symbol} follows from a final weighted score of "
        "{final_score:.1f}/100 across all available analysis modules, at {confidence:.1f}% "
        "confidence. {top_factor_clause}{conflict_tail}"
    ),
}

_LLM_INSTRUCTIONS = {
    "technical_reasoning": (
        "You are a professional equity analyst. Rewrite the following technical-analysis "
        "reasoning as a concise, natural-language paragraph for an investor. Do not invent any "
        "figures, indicators, or facts beyond what is stated -- only rephrase and clarify."
    ),
    "fundamental_reasoning": (
        "You are a professional equity analyst. Rewrite the following fundamental-analysis "
        "reasoning as a concise, natural-language paragraph for an investor. Do not invent any "
        "figures, ratios, or facts beyond what is stated -- only rephrase and clarify."
    ),
    "risk_explanation": (
        "You are a professional equity analyst. Rewrite the following risk assessment as a "
        "concise, natural-language paragraph for an investor. Do not invent any figures or facts "
        "beyond what is stated -- only rephrase and clarify."
    ),
}


class PromptTemplateManager:
    """Deterministic template rendering plus LLM-prompt construction.
    Stateless beyond the fixed template dictionaries above -- safe to
    share a single instance across requests."""

    def render(self, name: str, **kwargs) -> str:
        return _TEMPLATES[name].format(**kwargs)

    def build_prompt(self, name: str, baseline_text: str, **kwargs) -> str:
        """An LLM-oriented instruction string grounded in the
        deterministic baseline text for the same section, so an
        adapter is asked to rephrase known-correct content rather than
        generate facts of its own. Not called anywhere in production
        wiring today -- see llm_adapter.py."""
        instruction = _LLM_INSTRUCTIONS.get(name, "Rewrite the following investment analysis concisely.")
        return f"{instruction}\n\n{baseline_text}"

    def join_factors(self, factors: List[InterpretedFactor], max_factors: int = 3) -> str:
        """Turns the strongest `max_factors` factors into one flowing
        clause, e.g. "This is supported by strong RSI momentum and
        moderate volume confirmation." Returns an empty string for an
        empty list so callers can splice it into a sentence safely."""
        if not factors:
            return ""
        clauses = [f.description.rstrip(".") for f in factors[:max_factors]]
        if len(clauses) == 1:
            joined = clauses[0]
        elif len(clauses) == 2:
            joined = f"{clauses[0]} and {clauses[1]}"
        else:
            joined = f"{', '.join(clauses[:-1])}, and {clauses[-1]}"
        return f"This is supported by {joined[0].lower() + joined[1:]}."
