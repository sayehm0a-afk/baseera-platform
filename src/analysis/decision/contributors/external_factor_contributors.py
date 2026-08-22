"""Four ScoreContributors demonstrating the AI Decision Intelligence
Layer's extension point concretely, not just architecturally: News
Intelligence, Macro Economy, Insider Transactions, and Sector Rotation
(requirement 5's remaining future-module list, alongside Momentum/
Volume/Risk which are implemented in their own files since they need
real computation over TechnicalAnalysisResult).

No real Macro/Insider/Sector Rotation data vendor is contracted (same
disclosed-gap status as `SaudiMarketDataProvider` before SAHMK, or
`IFundamentalDataProvider` before a real fundamentals vendor) -- each
of those three reads its input from `AnalysisContext.extra`, a
free-form bag any future caller can populate once such a vendor
exists, and honestly reports itself unavailable (`score=None,
weight=0.0`) when that key is absent, exactly like
FundamentalScoreContributor already does for a missing ratio.

News Intelligence is the one exception (Phase 12): a real pipeline
now exists (`src.news_intelligence`), populating
`context.extra["news_sentiment"]` from real, LLM-analyzed
`NewsEvent` rows via `src.analysis.context_builder.build_analysis_context()`
-- this contributor itself is unchanged in *how* it reads that key
(still `context.extra["news_sentiment"]`, still honestly unavailable
when absent), only in what can now populate it. This is proven
end-to-end, not just asserted: the unit tests supply fake `extra` data
and confirm each contributor scores it correctly, and
AIDecisionEngine's own pluggability test does the same at the
orchestration level.

Every contributor here implements the same `ScoreContributor` protocol
already defined in src/analysis/recommendation/types.py -- nothing
about that protocol, `RecommendationEngine`, or any existing
contributor changes to add these.
"""

from typing import Any, Dict, List

from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection


class NewsSentimentScoreContributor:
    """Expects `context.extra["news_sentiment"] = {"sentiment_score":
    float in [-1, 1], "article_count": int}`, optionally with an
    `"events"` list (each `{"news_event_id", "headline", "category",
    "sentiment_score", "confidence", "impact_points"}` -- the exact
    shape `src.news_intelligence.service.NewsIntelligenceService.get_symbol_sentiment()`
    produces). When `events` is present, one Signal is emitted per
    event (citing its own headline/category/impact) instead of a
    single blended one, so `AIDecisionEngine`'s existing top-signals-
    by-impact explainability shows each news item individually --
    "Earnings news (+8.0 pts): ..." -- next to every other
    contributor's signals, without any change to that mechanism. The
    blended `score`/`confidence` math is identical either way; only
    which Signal objects carry the explanation changes."""

    name = "news_sentiment"

    def __init__(self, weight: float = 0.05):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        data = context.extra.get("news_sentiment")
        if not data or data.get("sentiment_score") is None:
            return ScoreContribution(
                source=self.name, score=None, weight=0.0, confidence=0.0, signals=[],
                notes="No news sentiment data was supplied for this symbol (context.extra['news_sentiment']).",
            )

        sentiment = max(-1.0, min(1.0, float(data["sentiment_score"])))
        article_count = int(data.get("article_count", 0) or 0)
        points = round(sentiment * 20.0, 1)
        score = max(0.0, min(100.0, 50.0 + points))
        confidence = round(min(100.0, article_count * 20.0), 1)

        events = data.get("events") or []
        if events:
            signals = [self._event_signal(event) for event in events]
        else:
            direction = (
                SignalDirection.BULLISH if points > 0 else SignalDirection.BEARISH if points < 0 else SignalDirection.NEUTRAL
            )
            signals = [
                Signal(
                    name="news_sentiment",
                    description=f"News sentiment score {sentiment:+.2f} across {article_count} article(s).",
                    direction=direction, source=self.name, impact=points,
                )
            ]

        return ScoreContribution(
            source=self.name, score=round(score, 1), weight=self.default_weight, confidence=confidence, signals=signals
        )

    def _event_signal(self, event: Dict[str, Any]) -> Signal:
        impact = float(event.get("impact_points", 0.0) or 0.0)
        category = str(event.get("category", "OTHER")).replace("_", " ").title()
        headline = str(event.get("headline", ""))
        sign = "+" if impact >= 0 else ""
        direction = SignalDirection.BULLISH if impact > 0 else SignalDirection.BEARISH if impact < 0 else SignalDirection.NEUTRAL
        return Signal(
            name=f"news_event:{event.get('news_event_id', '')}",
            description=f"{category} news ({sign}{impact:.1f} pts): {headline}",
            direction=direction, source=self.name, impact=impact,
        )


_MACRO_TREND_POINTS = {
    "tadawul_index_trend": {"up": 6.0, "down": -6.0, "flat": 0.0},
    "oil_price_trend": {"up": 5.0, "down": -5.0, "flat": 0.0},
    "interest_rate_trend": {"up": -4.0, "down": 4.0, "flat": 0.0},
}
_MACRO_TREND_LABELS = {
    "tadawul_index_trend": "Tadawul All-Share Index",
    "oil_price_trend": "Brent crude oil price",
    "interest_rate_trend": "SAMA policy interest rate",
}


class MacroEconomicScoreContributor:
    """Expects `context.extra["macro_indicators"] = {"tadawul_index_trend":
    "up"|"down"|"flat", "oil_price_trend": ..., "interest_rate_trend": ...}`
    -- any subset of these three keys; each recognized key is scored
    independently. Oil price and the broad index trend are scored as
    tailwinds for Tadawul-listed equities; a rising policy rate is
    scored as a headwind (higher borrowing/discount costs) -- standard,
    documented macro-to-equity directional assumptions, not derived
    from any live macro data source."""

    name = "macro"

    def __init__(self, weight: float = 0.05):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        data = context.extra.get("macro_indicators")
        if not data:
            return ScoreContribution(
                source=self.name, score=None, weight=0.0, confidence=0.0, signals=[],
                notes="No macroeconomic indicator data was supplied (context.extra['macro_indicators']).",
            )

        points = 0.0
        signals: List[Signal] = []
        computed = 0
        for key, buckets in _MACRO_TREND_POINTS.items():
            trend = data.get(key)
            if trend not in buckets:
                continue
            computed += 1
            pts = buckets[trend]
            points += pts
            direction = (
                SignalDirection.BULLISH if pts > 0 else SignalDirection.BEARISH if pts < 0 else SignalDirection.NEUTRAL
            )
            signals.append(
                Signal(
                    name=key, description=f"{_MACRO_TREND_LABELS[key]} trend: {trend}.",
                    direction=direction, source=self.name, impact=pts,
                )
            )

        if computed == 0:
            return ScoreContribution(
                source=self.name, score=None, weight=0.0, confidence=0.0, signals=[],
                notes="macro_indicators was supplied but contained no recognized trend keys.",
            )

        score = max(0.0, min(100.0, 50.0 + points))
        confidence = round(100.0 * (computed / len(_MACRO_TREND_POINTS)), 1)
        return ScoreContribution(
            source=self.name, score=round(score, 1), weight=self.default_weight, confidence=confidence, signals=signals
        )


class InsiderTransactionScoreContributor:
    """Expects `context.extra["insider_transactions"] = {"net_buy_value":
    float (SAR, positive = net buying), "transaction_count": int}`."""

    name = "insider_transactions"

    def __init__(self, weight: float = 0.03):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        data = context.extra.get("insider_transactions")
        if not data or data.get("net_buy_value") is None:
            return ScoreContribution(
                source=self.name, score=None, weight=0.0, confidence=0.0, signals=[],
                notes="No insider transaction data was supplied (context.extra['insider_transactions']).",
            )

        net_buy_value = float(data["net_buy_value"])
        transaction_count = int(data.get("transaction_count", 0) or 0)
        if net_buy_value > 0:
            points = 12.0 if net_buy_value >= 1_000_000 else 8.0
            direction = SignalDirection.BULLISH
        elif net_buy_value < 0:
            points = -12.0 if net_buy_value <= -1_000_000 else -8.0
            direction = SignalDirection.BEARISH
        else:
            points = 0.0
            direction = SignalDirection.NEUTRAL

        score = max(0.0, min(100.0, 50.0 + points))
        confidence = round(min(100.0, transaction_count * 25.0), 1)
        signal = Signal(
            name="insider_net_activity",
            description=f"Net insider activity: {net_buy_value:,.0f} SAR across {transaction_count} transaction(s).",
            direction=direction, source=self.name, impact=points,
        )
        return ScoreContribution(
            source=self.name, score=round(score, 1), weight=self.default_weight, confidence=confidence, signals=[signal]
        )


class SectorRotationScoreContributor:
    """Expects `context.extra["sector_rotation"] = {"sector_relative_strength":
    float in [-1, 1]}` -- this specific stock's trailing return relative
    to the average trailing return of its real Tadawul sector peers
    (Phase 3 area 4: activated via context_builder.py's
    `_sector_rotation_extra`, computed by
    `src.analysis.decision_v2.sector_strength.compute_sector_strength`;
    previously always `None` in production, see that module's own
    docstring for why). A single metric has no natural sample size to
    scale confidence by, so confidence is a fixed, documented value
    whenever the metric is present."""

    name = "sector_rotation"
    _FIXED_CONFIDENCE = 75.0

    def __init__(self, weight: float = 0.02):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        data = context.extra.get("sector_rotation")
        if not data or data.get("sector_relative_strength") is None:
            return ScoreContribution(
                source=self.name, score=None, weight=0.0, confidence=0.0, signals=[],
                notes="No sector rotation data was supplied (context.extra['sector_rotation']).",
            )

        strength = max(-1.0, min(1.0, float(data["sector_relative_strength"])))
        points = round(strength * 20.0, 1)
        score = max(0.0, min(100.0, 50.0 + points))
        direction = (
            SignalDirection.BULLISH if points > 0 else SignalDirection.BEARISH if points < 0 else SignalDirection.NEUTRAL
        )
        signal = Signal(
            name="sector_relative_strength",
            description=f"Sector relative strength vs. market: {strength:+.2f}.",
            direction=direction, source=self.name, impact=points,
        )
        return ScoreContribution(
            source=self.name, score=round(score, 1), weight=self.default_weight,
            confidence=self._FIXED_CONFIDENCE, signals=[signal],
        )
