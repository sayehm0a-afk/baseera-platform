"""PublicationGate: decides whether one symbol's already-computed
`SymbolScanOutcome` may be shown in a "this is a real opportunity"
ranking category (TOP_BUY, TOP_STRONG_BUY, TOP_LONG_TERM_INVESTMENT,
TOP_SWING_TRADE, NEW_OPPORTUNITIES) -- the missing step that let
symbol 1020 reach TOP_BUY #1 in the 2026-07-30 live scan purely by
having the highest `final_score`, with no check on whether the trade
it implied (buy at price, target above price, acceptable risk/reward)
actually made sense.

This module computes no new numbers. Every input it reads
(`target_price`, `stop_loss`, `expected_return_pct`,
`risk_reward_ratio`, `entry_quality`, `confidence`) already exists on
`InvestmentDecision` (src/analysis/decision/ai_decision_engine.py) --
this is a pure evaluation of evidence already produced, run at rank
time, not persisted (matching this whole layer's "computed on read"
convention, see ranking.py's own module docstring).

Two gates the wider mandate calls for -- sector-relative and
TASI/benchmark-relative evidence -- are recorded as `NOT_EVALUATED`
but deliberately never block publication: `AIDecisionEngine` does not
currently compute a sector-relative or benchmark-relative score at
all (no TASI integration exists yet, see docs/phase9_market_
intelligence/MARKET_INTELLIGENCE_REPORT.md), so there is no claim
being made that evidence could contradict. Blocking on the absence of
an input nothing downstream ever uses would just make every
recommendation NOT_EVALUATED for a reason unrelated to its actual
quality. What *is* enforced structurally: nothing in this module or
downstream ever manufactures a sector- or benchmark-relative claim
from these NOT_EVALUATED gates -- see PublicationEvaluation.disclosures.
"""

from datetime import datetime, timezone
from typing import List, Optional

from src.analysis.decision.types import EntryQuality, PositionSize
from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.config import (
    get_fundamental_conflict_margin,
    get_max_data_age_hours,
    get_max_spread_pct,
    get_min_average_traded_value,
    get_min_calibrated_success_probability,
    get_min_candles_for_recommendation,
    get_min_risk_reward_ratio,
    get_news_conflict_min_articles,
    get_news_conflict_sentiment_threshold,
)
from src.market_intelligence.types import (
    GateResult,
    GateStatus,
    PublicationEvaluation,
    PublicationStatus,
    SymbolScanOutcome,
)

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}
_SELL_LIKE = {Recommendation.SELL, Recommendation.STRONG_SELL}


def evaluate_publication(
    outcome: SymbolScanOutcome,
    calibrated_success_probability: Optional[float] = None,
) -> PublicationEvaluation:
    """`calibrated_success_probability` (0-1) is optional and defaults
    to `None` -- every existing caller (ranking.py, opportunity_ranking.py,
    watchlist.py, scan_progress.py) evaluates gates against a pure,
    in-memory `SymbolScanOutcome` with no DB session in scope, so they
    cannot look up whether a confidence-calibration model is active.
    Passing this value (computed once, at write time, where a session
    does exist -- see MarketIntelligenceRepository.save_symbol_records
    and src.ai_evolution.confidence_calibration.get_effective_confidence)
    is what activates the confidence_calibration gate for real; omitting
    it correctly reports NOT_EVALUATED rather than fabricating a
    calibration that was never actually computed for this call.
    """
    if not outcome.success or outcome.report is None:
        return PublicationEvaluation(
            status=PublicationStatus.INSUFFICIENT_DATA,
            gates=[GateResult(
                name="data_availability", status=GateStatus.FAIL,
                detail=outcome.skipped_reason or outcome.error or "no analyst report produced",
            )],
            disclosures=[],
        )

    gates: List[GateResult] = [GateResult(name="data_availability", status=GateStatus.PASS, detail="analyst report present")]
    disclosures: List[str] = []

    data_source_gate = _real_data_source_gate(outcome)
    gates.append(data_source_gate)
    if data_source_gate.status is GateStatus.FAIL:
        # Hard stop, checked before every other gate: synthetic data
        # must never reach a publication decision on any other merit.
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    gates.append(_freshness_gate(outcome))
    gates.append(_price_validity_gate(outcome))
    gates.append(_confidence_gate(outcome))
    gates.append(_targets_gate(outcome))
    gates.append(_min_candles_gate(outcome))
    gates.append(_suspension_gate(outcome))
    gates.append(_sector_data_gate(outcome, disclosures))
    gates.append(_benchmark_data_gate(disclosures))

    critical_fail = next((g for g in gates if g.status is GateStatus.FAIL), None)
    if critical_fail is not None:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    recommendation = outcome.recommendation
    is_actionable = recommendation in _BUY_LIKE or recommendation in _SELL_LIKE

    if not is_actionable:
        for name in (
            "risk_reward", "entry_quality", "abnormal_spread", "position_sizing",
            "news_conflict", "fundamental_conflict", "confidence_calibration",
        ):
            gates.append(GateResult(name=name, status=GateStatus.NOT_EVALUATED, detail="HOLD proposes no trade"))
        return PublicationEvaluation(status=PublicationStatus.PUBLISHED, gates=gates, disclosures=disclosures)

    risk_reward_gate = _risk_reward_gate(outcome, recommendation)
    gates.append(risk_reward_gate)
    if risk_reward_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    liquidity_gate = _liquidity_gate(outcome)
    gates.append(liquidity_gate)
    if liquidity_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    abnormal_spread_gate = _abnormal_spread_gate(outcome)
    gates.append(abnormal_spread_gate)
    if abnormal_spread_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    position_sizing_gate = _position_sizing_gate(outcome)
    gates.append(position_sizing_gate)
    if position_sizing_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    news_conflict_gate = _news_conflict_gate(outcome, recommendation)
    gates.append(news_conflict_gate)
    if news_conflict_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    fundamental_conflict_gate = _fundamental_conflict_gate(outcome, recommendation)
    gates.append(fundamental_conflict_gate)
    if fundamental_conflict_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    confidence_calibration_gate = _confidence_calibration_gate(calibrated_success_probability)
    gates.append(confidence_calibration_gate)
    if confidence_calibration_gate.status is GateStatus.FAIL:
        return PublicationEvaluation(status=PublicationStatus.REJECTED, gates=gates, disclosures=disclosures)

    entry_quality = outcome.report.decision.entry_quality
    entry_quality_gate = GateResult(
        name="entry_quality",
        status=GateStatus.FAIL if entry_quality is EntryQuality.POOR else GateStatus.PASS,
        detail=f"entry quality: {entry_quality.value}",
    )
    gates.append(entry_quality_gate)
    if entry_quality_gate.status is GateStatus.FAIL:
        # A poor entry does not invalidate the underlying thesis the way a
        # missing critical input or a bad risk/reward does -- downgraded to
        # WATCH_ONLY (adversarial case #12: "strong fundamentals but no
        # entry setup -> watchlist, not immediate BUY"), not rejected outright.
        return PublicationEvaluation(status=PublicationStatus.WATCH_ONLY, gates=gates, disclosures=disclosures)

    return PublicationEvaluation(status=PublicationStatus.PUBLISHED, gates=gates, disclosures=disclosures)


def _real_data_source_gate(outcome: SymbolScanOutcome) -> GateResult:
    """Strict real-data protection: a symbol explicitly marked
    synthetic (`SymbolScanOutcome.is_synthetic is True`, set by
    MarketScanner from the provider it was actually scanned with --
    see scanner.py) can never be published, regardless of how good its
    score otherwise looks. `None` (not `False`) means "not tracked for
    this outcome" -- true for every SymbolScanOutcome built by tests
    written before this field existed -- and is deliberately
    NOT_EVALUATED rather than a hard fail, so it never silently claims
    a record is real either; only an outcome the real scan pipeline
    explicitly confirmed as SAHMK-sourced (`is_synthetic is False`)
    passes."""
    if outcome.is_synthetic is True:
        return GateResult(
            name="real_data_source", status=GateStatus.FAIL,
            detail=f"synthetic data cannot be published (data_source={outcome.data_source})",
        )
    if outcome.is_synthetic is False:
        return GateResult(name="real_data_source", status=GateStatus.PASS, detail=f"data_source={outcome.data_source}")
    return GateResult(name="real_data_source", status=GateStatus.NOT_EVALUATED, detail="data source not tracked for this outcome")


def _freshness_gate(outcome: SymbolScanOutcome) -> GateResult:
    scanned_at = outcome.scanned_at
    if scanned_at.tzinfo is None:
        # Reconstructed outcomes (read_model.outcome_from_record) carry
        # whatever a DB row returns -- SQLite drops tzinfo entirely, and
        # this column is always written/read as UTC (see
        # SymbolIntelligenceRecord.evaluated_at), so a naive value is
        # treated as UTC rather than compared against an aware "now"
        # and raising.
        scanned_at = scanned_at.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - scanned_at).total_seconds() / 3600.0
    max_age = get_max_data_age_hours()
    if age_hours > max_age:
        return GateResult(
            name="data_freshness", status=GateStatus.FAIL,
            detail=f"scan is {age_hours:.1f}h old, exceeds the {max_age:.0f}h maximum",
        )
    return GateResult(name="data_freshness", status=GateStatus.PASS, detail=f"scan is {age_hours:.1f}h old")


def _price_validity_gate(outcome: SymbolScanOutcome) -> GateResult:
    if outcome.latest_price is not None and outcome.latest_price > 0:
        return GateResult(name="price_validity", status=GateStatus.PASS, detail=f"price={outcome.latest_price}")
    return GateResult(name="price_validity", status=GateStatus.FAIL, detail="no valid latest price")


def _confidence_gate(outcome: SymbolScanOutcome) -> GateResult:
    if outcome.confidence is not None:
        return GateResult(name="confidence_present", status=GateStatus.PASS, detail=f"confidence={outcome.confidence}")
    return GateResult(name="confidence_present", status=GateStatus.FAIL, detail="no confidence computed")


def _targets_gate(outcome: SymbolScanOutcome) -> GateResult:
    decision = outcome.report.decision
    if decision.target_price is not None and decision.stop_loss is not None and decision.expected_return_pct is not None:
        return GateResult(name="targets_present", status=GateStatus.PASS, detail="target/stop/expected-return computed")
    return GateResult(name="targets_present", status=GateStatus.FAIL, detail="target price or stop loss unavailable")


def _risk_reward_gate(outcome: SymbolScanOutcome, recommendation: Recommendation) -> GateResult:
    decision = outcome.report.decision
    expected_return_pct = decision.expected_return_pct
    risk_reward_ratio = decision.risk_reward_ratio

    if recommendation in _BUY_LIKE and expected_return_pct is not None and expected_return_pct <= 0:
        return GateResult(
            name="risk_reward", status=GateStatus.FAIL,
            detail=f"BUY with non-positive expected return ({expected_return_pct}%) -- target does not sit above entry",
        )
    if recommendation in _SELL_LIKE and expected_return_pct is not None and expected_return_pct >= 0:
        return GateResult(
            name="risk_reward", status=GateStatus.FAIL,
            detail=f"SELL with non-negative expected return ({expected_return_pct}%) -- target does not sit below entry",
        )

    min_ratio = get_min_risk_reward_ratio()
    if risk_reward_ratio is None:
        return GateResult(name="risk_reward", status=GateStatus.NOT_EVALUATED, detail="no stop distance to compute risk/reward")
    if risk_reward_ratio < min_ratio:
        return GateResult(
            name="risk_reward", status=GateStatus.FAIL,
            detail=f"risk/reward {risk_reward_ratio:.2f} below minimum {min_ratio:.2f}",
        )
    return GateResult(name="risk_reward", status=GateStatus.PASS, detail=f"risk/reward {risk_reward_ratio:.2f}")


def _liquidity_gate(outcome: SymbolScanOutcome) -> GateResult:
    """A technically clean setup in a stock nobody can actually trade
    at size is not a real opportunity -- see docs/basirah_
    intelligence_core/PHASE_0_REALITY_AUDIT.md defect #1. Threshold is
    a conservative placeholder (get_min_average_traded_value), not yet
    empirically calibrated or horizon-specific; disclosed as a known
    limitation rather than presented as validated."""
    average_traded_value = outcome.average_traded_value
    if average_traded_value is None:
        return GateResult(name="liquidity", status=GateStatus.NOT_EVALUATED, detail="average volume unavailable")
    min_value = get_min_average_traded_value()
    if average_traded_value < min_value:
        return GateResult(
            name="liquidity", status=GateStatus.FAIL,
            detail=f"average traded value ~{average_traded_value:,.0f} SAR/day below minimum {min_value:,.0f}",
        )
    return GateResult(name="liquidity", status=GateStatus.PASS, detail=f"average traded value ~{average_traded_value:,.0f} SAR/day")


def _min_candles_gate(outcome: SymbolScanOutcome) -> GateResult:
    """`bars_used` is threaded through AnalysisContext.extra by
    context_builder.py (`len(df)` of the daily OHLCV history actually
    loaded) -- distinct from TechnicalAnalysisEngine's own internal
    35-row floor (below which the technical leg doesn't run at all and
    the symbol never reaches this gate as insufficient_data). This
    catches the case that floor doesn't: a symbol with just enough
    history to compute indicators but not enough for a trustworthy
    multi-month read (e.g. a recent IPO)."""
    context = outcome.context
    bars_used = context.extra.get("bars_used") if context is not None else None
    if bars_used is None:
        return GateResult(name="min_candles", status=GateStatus.NOT_EVALUATED, detail="bar count not tracked for this outcome")
    min_candles = get_min_candles_for_recommendation()
    if bars_used < min_candles:
        return GateResult(
            name="min_candles", status=GateStatus.FAIL,
            detail=f"only {bars_used} daily bars of history, minimum {min_candles} required for a reliable recommendation",
        )
    return GateResult(name="min_candles", status=GateStatus.PASS, detail=f"{bars_used} daily bars of history")


def _suspension_gate(outcome: SymbolScanOutcome) -> GateResult:
    """`likely_suspended` is a real, computed-from-real-data proxy
    (see context_builder._detect_likely_suspended) -- SAHMK exposes no
    explicit trading-status field."""
    context = outcome.context
    likely_suspended = context.extra.get("likely_suspended") if context is not None else None
    if likely_suspended is None:
        return GateResult(
            name="suspension", status=GateStatus.NOT_EVALUATED,
            detail="insufficient recent history to judge trading activity",
        )
    if likely_suspended:
        return GateResult(
            name="suspension", status=GateStatus.FAIL,
            detail="zero volume and an unchanged close across the most recent sessions -- likely suspended or halted",
        )
    return GateResult(name="suspension", status=GateStatus.PASS, detail="recent volume/price activity looks normal")


def _abnormal_spread_gate(outcome: SymbolScanOutcome) -> GateResult:
    """Real bid/ask from SAHMK's quote endpoint (see
    docs/SAHMK_INTEGRATION.md's verified field list) -- a wide spread
    means the visible price is not one a real order could actually
    fill near, the same "not really tradeable" concern the liquidity
    gate addresses via traded value."""
    context = outcome.context
    quote = (context.extra.get("quote") or {}) if context is not None else {}
    bid, ask = quote.get("bid"), quote.get("ask")
    if bid is None or ask is None or bid <= 0:
        return GateResult(name="abnormal_spread", status=GateStatus.NOT_EVALUATED, detail="bid/ask not available for this quote")
    spread_pct = (ask - bid) / bid * 100.0
    max_spread = get_max_spread_pct()
    if spread_pct > max_spread:
        return GateResult(
            name="abnormal_spread", status=GateStatus.FAIL,
            detail=f"bid/ask spread {spread_pct:.2f}% exceeds the maximum {max_spread:.2f}%",
        )
    return GateResult(name="abnormal_spread", status=GateStatus.PASS, detail=f"bid/ask spread {spread_pct:.2f}%")


def _position_sizing_gate(outcome: SymbolScanOutcome) -> GateResult:
    """A BUY/SELL that survived every gate above but whose own position
    sizer concluded no viable position exists (PositionSize.NONE --
    see src.analysis.decision.position_sizer, driven by e.g. stop
    distance too wide for the configured risk budget) must not be
    published as an actionable call with nothing to size it against."""
    position_size = outcome.position_size
    if position_size is None:
        return GateResult(name="position_sizing", status=GateStatus.NOT_EVALUATED, detail="no position size computed")
    if position_size is PositionSize.NONE:
        return GateResult(
            name="position_sizing", status=GateStatus.FAIL,
            detail="position sizer found no viable position size for this recommendation",
        )
    return GateResult(name="position_sizing", status=GateStatus.PASS, detail=f"position size: {position_size.value}")


def _news_conflict_gate(outcome: SymbolScanOutcome, recommendation: Recommendation) -> GateResult:
    """`news_sentiment` (NewsIntelligenceService.get_symbol_sentiment,
    -1..1 scale) is threaded through AnalysisContext.extra by
    context_builder.py. A strongly negative-sentiment BUY (or
    strongly positive-sentiment SELL), backed by enough real analyzed
    articles to not be single-headline noise, is a real contradiction
    a human analyst would not publish over silently."""
    context = outcome.context
    news = (context.extra.get("news_sentiment") if context is not None else None) or {}
    sentiment = news.get("sentiment_score")
    article_count = news.get("article_count", 0)
    min_articles = get_news_conflict_min_articles()
    if sentiment is None or article_count < min_articles:
        return GateResult(
            name="news_conflict", status=GateStatus.NOT_EVALUATED,
            detail=f"only {article_count} analyzed article(s) for this symbol, need at least {min_articles}",
        )
    threshold = get_news_conflict_sentiment_threshold()
    if recommendation in _BUY_LIKE and sentiment <= -threshold:
        return GateResult(
            name="news_conflict", status=GateStatus.FAIL,
            detail=f"BUY-like recommendation but aggregate news sentiment is {sentiment:.2f} (strongly negative, {article_count} articles)",
        )
    if recommendation in _SELL_LIKE and sentiment >= threshold:
        return GateResult(
            name="news_conflict", status=GateStatus.FAIL,
            detail=f"SELL-like recommendation but aggregate news sentiment is {sentiment:.2f} (strongly positive, {article_count} articles)",
        )
    return GateResult(name="news_conflict", status=GateStatus.PASS, detail=f"news sentiment {sentiment:.2f} does not contradict the recommendation")


def _fundamental_conflict_gate(outcome: SymbolScanOutcome, recommendation: Recommendation) -> GateResult:
    """`fundamental_score` (0-100, 50 neutral) is the fundamental
    contributor's own already-computed opinion (SymbolScanOutcome.
    fundamental_score, reconstructed from DecisionFactorBreakdown --
    never recomputed here). A BUY resting on technical/momentum
    strength while the fundamentals module is actively bearish (and
    vice versa for SELL) is a real, disclosed contradiction."""
    fundamental_score = outcome.fundamental_score
    if fundamental_score is None:
        return GateResult(name="fundamental_conflict", status=GateStatus.NOT_EVALUATED, detail="no fundamental score available for this symbol")
    margin = get_fundamental_conflict_margin()
    if recommendation in _BUY_LIKE and fundamental_score <= 50.0 - margin:
        return GateResult(
            name="fundamental_conflict", status=GateStatus.FAIL,
            detail=f"BUY-like recommendation but fundamental score is {fundamental_score:.1f} (bearish)",
        )
    if recommendation in _SELL_LIKE and fundamental_score >= 50.0 + margin:
        return GateResult(
            name="fundamental_conflict", status=GateStatus.FAIL,
            detail=f"SELL-like recommendation but fundamental score is {fundamental_score:.1f} (bullish)",
        )
    return GateResult(
        name="fundamental_conflict", status=GateStatus.PASS,
        detail=f"fundamental score {fundamental_score:.1f} does not contradict the recommendation",
    )


def _confidence_calibration_gate(calibrated_success_probability: Optional[float]) -> GateResult:
    """See evaluate_publication()'s docstring for why this value must
    be passed in rather than looked up here -- this function stays a
    pure, no-I/O gate like every other one in this module."""
    if calibrated_success_probability is None:
        return GateResult(
            name="confidence_calibration", status=GateStatus.NOT_EVALUATED,
            detail="no active confidence-calibration model applied for this evaluation",
        )
    min_probability = get_min_calibrated_success_probability()
    if calibrated_success_probability < min_probability:
        return GateResult(
            name="confidence_calibration", status=GateStatus.FAIL,
            detail=f"calibrated success probability {calibrated_success_probability:.0%} below minimum {min_probability:.0%}",
        )
    return GateResult(
        name="confidence_calibration", status=GateStatus.PASS,
        detail=f"calibrated success probability {calibrated_success_probability:.0%}",
    )


def _sector_data_gate(outcome: SymbolScanOutcome, disclosures: List[str]) -> GateResult:
    if outcome.sector:
        return GateResult(name="sector_data", status=GateStatus.PASS, detail=outcome.sector)
    disclosures.append("no sector classification available for this symbol -- no sector-relative claim is made")
    return GateResult(name="sector_data", status=GateStatus.NOT_EVALUATED, detail="sector unknown")


def _benchmark_data_gate(disclosures: List[str]) -> GateResult:
    disclosures.append("TASI/benchmark integration does not exist yet -- no market-relative claim is made")
    return GateResult(name="benchmark_data", status=GateStatus.NOT_EVALUATED, detail="TASI not integrated")


def is_publishable(outcome: SymbolScanOutcome) -> bool:
    return evaluate_publication(outcome).status is PublicationStatus.PUBLISHED
