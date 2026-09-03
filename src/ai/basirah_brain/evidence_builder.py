"""Builds a `BasirahBrainInputV1` from a real, already-computed
`DecisionResult` (src.analysis.decision_v2.types) plus its `Stock` row --
never recomputes any analysis itself, never calls SAHMK, never touches
the network. This is the sole boundary between Basirah's existing,
unmodified deterministic engine and the Brain's structured evidence
contract.

Optional parameters (`daily_bars`, `news_headlines`, `sector_performance`,
etc.) cover evidence that is genuinely available somewhere in the
system but not carried on `DecisionResult` itself (e.g. raw OHLCV bars
live on the technical-analysis DataFrame, not the decision object) --
callers that have that context may pass it in. Every one of them
defaults to `None`/empty and is recorded in `data_quality.missing_fields`
when omitted, per the architecture audit's explicit instruction: never
fabricate a field Basirah does not actually have.
"""

from typing import List, Optional, Sequence

from src.analysis.decision_v2.types import DecisionResult
from src.domain.models import Stock

from .schemas import (
    BasirahBrainInputV1,
    BrainDataQualityIn,
    BrainEventRisk,
    BrainExistingEngineEvidence,
    BrainFundamentals,
    BrainGateOutcomeEvidence,
    BrainIdentity,
    BrainMarketContext,
    BrainNewsEvidence,
    BrainNewsHeadline,
    BrainOhlcvBar,
    BrainPriceContext,
    BrainTechnicalEvidence,
)

# The real, stable key shape build_fundamental_summary() always returns
# (src/analysis/decision_v2/fundamental_summary.py) -- grouped here into
# the four evidence buckets the Brain schema exposes. Never invents a
# category breakdown finer than what the existing engine actually
# computed.
_GROWTH_KEYS = ("revenue_growth", "profit_growth", "eps_growth")
_PROFITABILITY_KEYS = ("net_profit_margin", "gross_profit_margin", "return_on_equity")
_BALANCE_SHEET_KEYS = ("debt_to_equity",)
_VALUATION_KEYS = ("price_to_earnings", "price_to_book", "dividend_yield")


def _format_ratio_group(summary: dict, keys: Sequence[str]) -> Optional[str]:
    parts = [f"{key}={summary.get(key)}" for key in keys if key in summary]
    if not parts or all(summary.get(key) is None for key in keys):
        return None
    return ", ".join(parts)


class OhlcvBarLike:
    """Structural placeholder documenting what `daily_bars`/`weekly_bars`
    entries must provide -- any object with these attributes (a
    `PriceBar` ORM row, a namedtuple, a dict-backed shim) works; this
    class is never instantiated, only used for the type hint's intent."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]


def _bars_to_schema(bars: Optional[Sequence[object]]) -> List[BrainOhlcvBar]:
    if not bars:
        return []
    out: List[BrainOhlcvBar] = []
    for bar in bars:
        out.append(
            BrainOhlcvBar(
                date=str(getattr(bar, "date", getattr(bar, "timestamp", ""))),
                open=float(getattr(bar, "open")),
                high=float(getattr(bar, "high")),
                low=float(getattr(bar, "low")),
                close=float(getattr(bar, "close")),
                volume=(
                    float(getattr(bar, "volume")) if getattr(bar, "volume", None) is not None else None
                ),
            )
        )
    return out


def build_input(
    decision_result: DecisionResult,
    stock: Stock,
    *,
    daily_bars: Optional[Sequence[object]] = None,
    weekly_bars: Optional[Sequence[object]] = None,
    news_headlines: Optional[Sequence[BrainNewsHeadline]] = None,
    index_direction: Optional[str] = None,
    index_strength: Optional[float] = None,
    sector_performance: Optional[str] = None,
    breakout_status: Optional[str] = None,
) -> BasirahBrainInputV1:
    """Pure, synchronous, zero-I/O construction of the Brain's structured
    evidence package. `decision_result`/`stock` must already exist
    (produced by the existing, unmodified DecisionEngineV2 pipeline);
    this function only reshapes already-computed evidence."""

    missing_fields: List[str] = []

    if daily_bars is None:
        missing_fields.append("price_context.recent_daily_bars")
    if weekly_bars is None:
        missing_fields.append("price_context.recent_weekly_bars")
    if news_headlines is None:
        missing_fields.append("news.recent_headlines")
    if index_direction is None:
        missing_fields.append("market_context.index_direction")
    if index_strength is None:
        missing_fields.append("market_context.index_strength")
    if sector_performance is None:
        missing_fields.append("market_context.sector_performance")
    # Architecture-audit-confirmed dead stub (SectorRotationScoreContributor
    # never receives real data) -- always missing today, not caller-supplied.
    missing_fields.append("market_context.relative_strength_vs_sector")
    # No earnings-calendar ingestion exists anywhere in the codebase today.
    missing_fields.append("event_risk.next_earnings_date")
    missing_fields.append("event_risk.days_to_earnings")

    identity = BrainIdentity(
        symbol=decision_result.symbol,
        company_name=decision_result.company_name_ar or decision_result.company_name_en,
        sector=decision_result.sector_ar or getattr(stock, "sector", None),
        timestamp=decision_result.decision_timestamp.isoformat(),
        market_session_status=decision_result.market_status,
    )

    price_context = BrainPriceContext(
        current_price=decision_result.current_price,
        previous_close=None,
        price_change_pct=None,
        recent_daily_bars=_bars_to_schema(daily_bars),
        recent_weekly_bars=_bars_to_schema(weekly_bars) if weekly_bars is not None else None,
        data_freshness_status=decision_result.data_freshness_status.value,
        quote_timestamp=(
            decision_result.quote_timestamp.isoformat() if decision_result.quote_timestamp else None
        ),
    )

    support_levels = [
        lvl
        for lvl in (decision_result.nearest_support, decision_result.major_support)
        if lvl is not None
    ]
    resistance_levels = [
        lvl
        for lvl in (decision_result.nearest_resistance, decision_result.major_resistance)
        if lvl is not None
    ]

    technical = BrainTechnicalEvidence(
        trend_state=decision_result.trend_direction_ar or None,
        trend_score=decision_result.sub_scores.trend_score,
        momentum_score=decision_result.sub_scores.momentum_score,
        volatility_score=decision_result.sub_scores.volatility_score,
        atr_pct=None,
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        current_volume=decision_result.current_volume,
        average_volume=decision_result.average_volume,
        relative_volume=decision_result.relative_volume,
        liquidity_quality=decision_result.liquidity_quality_ar or None,
        breakout_status=breakout_status,
        entry_quality=decision_result.entry_quality,
        anti_chase_state=(
            decision_result.entry_status.value if decision_result.entry_status is not None else None
        ),
    )
    if breakout_status is None:
        missing_fields.append("technical.breakout_status")

    market_context = BrainMarketContext(
        market_regime_state=decision_result.market_risk_state,
        market_regime_basis=decision_result.market_risk_basis_ar or None,
        market_regime_entry_permitted=decision_result.market_risk_entry_permitted,
        index_direction=index_direction,
        index_strength=index_strength,
        sector_performance=sector_performance,
        relative_strength_vs_sector=None,
    )

    fundamentals_dict = decision_result.fundamental_summary or {}
    fundamentals = BrainFundamentals(
        valuation_summary=_format_ratio_group(fundamentals_dict, _VALUATION_KEYS),
        growth_summary=_format_ratio_group(fundamentals_dict, _GROWTH_KEYS),
        profitability_summary=_format_ratio_group(fundamentals_dict, _PROFITABILITY_KEYS),
        balance_sheet_summary=_format_ratio_group(fundamentals_dict, _BALANCE_SHEET_KEYS),
        fundamental_score=None,  # Decision V2's 8 sub-scores do not include a dedicated fundamental score
        missing_data_flags=(
            [] if fundamentals_dict else ["fundamentals.all"]
        ),
    )

    news = BrainNewsEvidence(
        recent_headlines=list(news_headlines) if news_headlines else [],
        aggregate_sentiment_score=None,
        impact_label=decision_result.news_impact or None,
        impact_summary=decision_result.news_impact_summary_ar or None,
        article_count=len(news_headlines) if news_headlines else 0,
        missing_data_flags=([] if news_headlines else ["news.recent_headlines"]),
    )

    event_risk = BrainEventRisk(
        next_earnings_date=None,
        days_to_earnings=None,
        known_corporate_action=None,
    )

    reasons = list(
        dict.fromkeys((decision_result.why_not_buy_reasons or []) + (decision_result.negative_reasons or []))
    )

    existing_engine = BrainExistingEngineEvidence(
        deterministic_decision=decision_result.decision.value,
        deterministic_confidence_score=decision_result.confidence_score,
        opportunity_quality_score=decision_result.opportunity_quality_score,
        risk_score=decision_result.risk_score,
        entry_zone_low=decision_result.entry_zone_low,
        entry_zone_high=decision_result.entry_zone_high,
        stop_loss=decision_result.stop_loss,
        target_1=decision_result.target_1,
        target_2=decision_result.target_2,
        target_3=decision_result.target_3,
        holding_horizon_min_days=decision_result.expected_holding_period_min_days,
        holding_horizon_max_days=decision_result.expected_holding_period_max_days,
        risk_reward_target_1=decision_result.risk_reward_target_1,
        sub_scores={
            "trend_score": decision_result.sub_scores.trend_score,
            "momentum_score": decision_result.sub_scores.momentum_score,
            "volume_score": decision_result.sub_scores.volume_score,
            "liquidity_score": decision_result.sub_scores.liquidity_score,
            "volatility_score": decision_result.sub_scores.volatility_score,
            "risk_reward_score": decision_result.sub_scores.risk_reward_score,
            "market_context_score": decision_result.sub_scores.market_context_score,
            "data_quality_score": decision_result.sub_scores.data_quality_score,
        },
        gate_outcomes=[
            BrainGateOutcomeEvidence(
                name=g.name, status=g.status.value, detail=g.detail, blocking=bool(g.blocking)
            )
            for g in decision_result.gates
        ],
        rejection_or_watch_reasons=reasons,
        invalidation_conditions=list(decision_result.invalidation_conditions or []),
    )

    data_quality = BrainDataQualityIn(
        stale_flags=(
            [] if decision_result.data_freshness_status.value == "LIVE" else [decision_result.data_freshness_status.value]
        ),
        missing_fields=missing_fields,
        is_synthetic=not decision_result.is_real_data,
        provider_status=decision_result.data_source,
    )

    return BasirahBrainInputV1(
        identity=identity,
        price_context=price_context,
        technical=technical,
        market_context=market_context,
        fundamentals=fundamentals,
        news=news,
        event_risk=event_risk,
        existing_engine=existing_engine,
        data_quality=data_quality,
    )
