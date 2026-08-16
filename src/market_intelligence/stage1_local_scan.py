"""Stage 1 of the two-stage Radar scan (Basirah Radar V2, SAHMK quota
optimization mandate, 2026-08-16): narrows the full eligible Saudi-market
universe down to a smaller, *ranked* set of genuine candidates using
ONLY already-persisted local data -- zero SAHMK requests, no matter how
large the universe is.

Reuses, rather than reimplements, everything that already exists:
`SymbolSelector` for universe resolution (same DB-only query the
scheduler itself uses), `load_price_bars` for OHLCV (DB-only),
`TechnicalAnalysisEngine` for every indicator (the same engine every
other decision path in this codebase already runs), and Decision Engine
V2's own scoring/evidence modules
(`src.analysis.decision_v2.scoring`/`evidence`) for both the six
composite sub-scores (trend, momentum, volume, liquidity, volatility,
risk/reward potential) and the support/resistance + accumulation/
distribution evidence -- the identical functions the live decision
pipeline already uses, not a parallel scoring engine. The only
genuinely new logic here is the local-only "current price/volume"
substitution: everywhere else in this codebase, "current" price/volume
comes from a live quote (`context.extra["quote"]`); Stage 1 has no live
quote by design, so it uses the most recent already-ingested PriceBar's
close/volume instead -- the same figures the once-daily OHLCV sync (see
market_data.ingestion.config) already keeps fresh in the database.

Candidate selection is threshold-based, not a fixed top-N cut (per the
mandate: "Do not hard-code these numbers without evidence") -- a
symbol becomes a candidate when it passes a liquidity floor AND at
least one genuine local signal fires (abnormal volume, a trending ADX
reading, an RSI extreme, a resistance breakout, or an accumulation/
distribution read). The real number of candidates a given day's
universe produces is meant to be *measured*, not decided in advance;
see the admin GET .../stage1-scan route this module backs for exactly
that measurement. Within that candidate set, `ranking_score` (0-100,
see `_composite_ranking_score`) orders which candidates are the
strongest -- this is what lets Radar V2's orchestrator hand only the
best few to Stage 2's bounded live validation instead of the entire
candidate set.

Every threshold used below (signal thresholds, ATR-based risk/reward
multiples, and the six ranking_score weights) is read from
`src.market_intelligence.config` at call time -- see that module's own
"Basirah Radar V2" section for each threshold's default value, exact
meaning, and disclosed calibration status. None are hard-coded module
constants presented as proven; all are configurable without a code
change once real forward-tested evidence exists to justify retuning
them (see src.ai_evolution / src.backtesting for that future
calibration work).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.analysis.decision_v2 import scoring
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.evidence import derive_accumulation_evidence, derive_support_resistance
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.domain.models import Stock, Timeframe
from src.market_intelligence.config import (
    get_min_average_traded_value,
    get_min_risk_reward_ratio,
    get_stage1_abnormal_volume_ratio,
    get_stage1_atr_reward_multiple,
    get_stage1_atr_risk_multiple,
    get_stage1_liquidity_weight,
    get_stage1_min_dollar_volume_sar,
    get_stage1_momentum_weight,
    get_stage1_risk_reward_weight,
    get_stage1_rsi_overbought,
    get_stage1_rsi_oversold,
    get_stage1_trend_weight,
    get_stage1_trending_adx_threshold,
    get_stage1_volatility_weight,
    get_stage1_volume_weight,
)
from src.market_intelligence.symbol_selector import SymbolSelector

# TechnicalAnalysisEngine.analyze()'s own minimum-rows requirement
# (MACD's 26+9 warm-up is the longest) -- a symbol with fewer bars than
# this cannot be scored at all, not a Stage-1-specific choice, so it
# stays a plain module constant rather than a configurable threshold.
MIN_INDICATOR_ROWS = 35


@dataclass(frozen=True)
class Stage1Signal:
    name: str
    detail_ar: str


@dataclass(frozen=True)
class Stage1ComponentScores:
    """The six sub-scores that make up `ranking_score`, each 0-100 (50
    = neutral/unknown), exactly as `opportunity_quality_score` combines
    them -- surfaced individually so a caller (or a future explainability
    UI) can see WHY one candidate outranked another, not just the final
    number."""

    trend: Optional[float] = None
    momentum: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    volatility: Optional[float] = None
    risk_reward: Optional[float] = None


@dataclass(frozen=True)
class Stage1SymbolResult:
    symbol: str
    is_candidate: bool
    skip_reason: Optional[str] = None
    latest_close: Optional[float] = None
    latest_bar_timestamp: Optional[datetime] = None
    dollar_volume: Optional[float] = None
    relative_volume: Optional[float] = None
    adx_14: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_pct: Optional[float] = None
    signals: List[Stage1Signal] = field(default_factory=list)
    ranking_score: Optional[float] = None
    component_scores: Stage1ComponentScores = field(default_factory=Stage1ComponentScores)
    risk_reward_ratio: Optional[float] = None


@dataclass(frozen=True)
class Stage1ScanResult:
    universe_size: int
    evaluated_count: int
    skipped_count: int
    candidate_count: int
    candidates: List[Stage1SymbolResult]
    all_results: List[Stage1SymbolResult]


def _score_symbol(symbol: str, session: Session, stock_id: int) -> Stage1SymbolResult:
    df = load_price_bars(session, stock_id, Timeframe.ONE_DAY)
    if len(df) < MIN_INDICATOR_ROWS:
        return Stage1SymbolResult(symbol=symbol, is_candidate=False, skip_reason="insufficient_history")

    result = TechnicalAnalysisEngine().analyze(df)

    latest_close = float(df["close"].iloc[-1])
    latest_volume = float(df["volume"].iloc[-1])
    latest_bar_timestamp = df.index[-1].to_pydatetime()

    volume_sma = result.get("volume_sma_20").latest()
    relative_volume = (
        latest_volume / volume_sma if volume_sma is not None and volume_sma > 0 else None
    )
    adx = result.get("adx_14").latest()
    rsi = result.get("rsi_14").latest()
    atr = result.get("atr_14").latest()
    atr_pct = (atr / latest_close * 100.0) if atr is not None and latest_close else None
    atr_ratio = (atr / latest_close) if atr is not None and latest_close else None
    dollar_volume = latest_close * latest_volume
    # 20-period average traded value (price x average volume) -- the
    # same formula src.analysis.decision_v2.engine.py uses for its own
    # `average_traded_value`, distinct from `dollar_volume` above
    # (a single-bar figure used for the liquidity floor/skip_reason,
    # unchanged from before this composite score was added).
    average_traded_value = latest_close * volume_sma if volume_sma is not None else None

    sr_evidence = derive_support_resistance(latest_close, result.support_resistance)
    breakout = sr_evidence.breakout_level is not None and latest_close > sr_evidence.breakout_level

    abnormal_volume_ratio = get_stage1_abnormal_volume_ratio()
    trending_adx_threshold = get_stage1_trending_adx_threshold()
    rsi_oversold = get_stage1_rsi_oversold()
    rsi_overbought = get_stage1_rsi_overbought()

    signals: List[Stage1Signal] = []
    if relative_volume is not None and relative_volume >= abnormal_volume_ratio:
        signals.append(
            Stage1Signal("abnormal_volume", f"حجم تداول أعلى من المعتاد ({relative_volume:.1f}x المتوسط)")
        )
    if adx is not None and adx >= trending_adx_threshold:
        signals.append(Stage1Signal("trending", f"اتجاه قوي (ADX = {adx:.1f})"))
    if rsi is not None and rsi <= rsi_oversold:
        signals.append(Stage1Signal("rsi_oversold", f"منطقة تشبع بيعي (RSI = {rsi:.1f})"))
    if rsi is not None and rsi >= rsi_overbought:
        signals.append(Stage1Signal("rsi_overbought", f"منطقة تشبع شرائي (RSI = {rsi:.1f})"))
    if breakout:
        signals.append(Stage1Signal("resistance_breakout", "اختراق أقرب مستوى مقاومة"))

    volume_component = scoring.volume_score(result)
    accumulation = derive_accumulation_evidence(volume_component, relative_volume, direction=0)
    if accumulation.accumulation_score is not None and accumulation.accumulation_score >= 60.0:
        signals.append(Stage1Signal("accumulation", accumulation.assessment_ar))
    elif accumulation.accumulation_score is not None and accumulation.accumulation_score <= 40.0:
        signals.append(Stage1Signal("distribution", accumulation.assessment_ar))

    trend_component = scoring.trend_score(result, latest_close)
    momentum_component = scoring.momentum_score(result)
    liquidity_component = scoring.liquidity_score(average_traded_value, get_min_average_traded_value())
    volatility_component = scoring.volatility_score(atr_ratio, DecisionV2Tuning())
    risk_reward_ratio = _potential_risk_reward_ratio(latest_close, atr, sr_evidence)
    risk_reward_component = scoring.risk_reward_score(risk_reward_ratio, get_min_risk_reward_ratio())

    stage1_tuning = DecisionV2Tuning(
        trend_weight=get_stage1_trend_weight(),
        momentum_weight=get_stage1_momentum_weight(),
        volume_weight=get_stage1_volume_weight(),
        liquidity_weight=get_stage1_liquidity_weight(),
        volatility_weight=get_stage1_volatility_weight(),
        risk_reward_weight=get_stage1_risk_reward_weight(),
        market_context_weight=0.0,
        data_quality_weight=0.0,
    )
    ranking_score = scoring.opportunity_quality_score(
        {
            "trend_score": trend_component,
            "momentum_score": momentum_component,
            "volume_score": volume_component,
            "liquidity_score": liquidity_component,
            "volatility_score": volatility_component,
            "risk_reward_score": risk_reward_component,
            "market_context_score": None,
            "data_quality_score": None,
        },
        stage1_tuning,
    )

    min_dollar_volume = get_stage1_min_dollar_volume_sar()
    passes_liquidity = dollar_volume >= min_dollar_volume
    is_candidate = passes_liquidity and len(signals) > 0

    return Stage1SymbolResult(
        symbol=symbol,
        is_candidate=is_candidate,
        skip_reason=None if passes_liquidity else "below_liquidity_floor",
        latest_close=latest_close,
        latest_bar_timestamp=latest_bar_timestamp,
        dollar_volume=dollar_volume,
        relative_volume=relative_volume,
        adx_14=adx,
        rsi_14=rsi,
        atr_pct=atr_pct,
        signals=signals,
        ranking_score=ranking_score if is_candidate else None,
        component_scores=Stage1ComponentScores(
            trend=trend_component,
            momentum=momentum_component,
            volume=volume_component,
            liquidity=liquidity_component,
            volatility=volatility_component,
            risk_reward=risk_reward_component,
        ),
        risk_reward_ratio=risk_reward_ratio,
    )


def _potential_risk_reward_ratio(price: float, atr: Optional[float], sr_evidence) -> Optional[float]:
    """A rough, ranking-only reward:risk estimate -- never a committed
    price plan (Stage 2 / Decision Engine V2's own target/stop
    derivation is the real, published one). Prefers real locally-
    detected support/resistance levels as the potential target/stop;
    falls back to configurable ATR multiples when a level isn't
    available on that side. `None` whenever neither ATR nor a usable
    level exists, or the resulting structure is degenerate (target at
    or below price, or stop at or above price)."""
    if price is None or price <= 0:
        return None

    potential_target = sr_evidence.nearest_resistance
    if potential_target is None and atr is not None and atr > 0:
        potential_target = price + atr * get_stage1_atr_reward_multiple()

    potential_stop = sr_evidence.nearest_support
    if potential_stop is None and atr is not None and atr > 0:
        potential_stop = price - atr * get_stage1_atr_risk_multiple()

    if potential_target is None or potential_stop is None:
        return None
    if potential_target <= price or potential_stop >= price:
        return None

    return round((potential_target - price) / (price - potential_stop), 2)


def run_stage1_local_scan(session: Session, symbols: Optional[List[str]] = None) -> Stage1ScanResult:
    """Scores the full eligible universe (or an explicit `symbols`
    list, for testing/narrower runs) using only already-persisted
    local data. Makes zero calls to any market-data provider --
    `SymbolSelector.select()` and `load_price_bars()` are both
    DB-only, and `TechnicalAnalysisEngine` is pure computation over an
    already-loaded DataFrame."""
    if symbols is None:
        symbols = SymbolSelector().select(session)

    universe_size = len(symbols)
    stock_ids_by_symbol = {
        row.symbol: row.id for row in session.query(Stock.id, Stock.symbol).filter(Stock.symbol.in_(symbols)).all()
    }

    all_results: List[Stage1SymbolResult] = []
    skipped = 0
    for symbol in symbols:
        stock_id = stock_ids_by_symbol.get(symbol)
        if stock_id is None:
            all_results.append(Stage1SymbolResult(symbol=symbol, is_candidate=False, skip_reason="no_stock_row"))
            skipped += 1
            continue
        scored = _score_symbol(symbol, session, stock_id)
        all_results.append(scored)
        if scored.skip_reason == "insufficient_history":
            skipped += 1

    candidates = sorted(
        (r for r in all_results if r.is_candidate),
        # ranking_score is the primary order (the composite signal this
        # module exists to produce); signal count is only a tie-breaker
        # for the (rare) case of two candidates landing on the exact
        # same score, so ordering never silently degrades to the old
        # signal-count-only behavior.
        key=lambda r: (r.ranking_score if r.ranking_score is not None else -1.0, len(r.signals)),
        reverse=True,
    )

    return Stage1ScanResult(
        universe_size=universe_size,
        evaluated_count=universe_size - skipped,
        skipped_count=skipped,
        candidate_count=len(candidates),
        candidates=candidates,
        all_results=all_results,
    )
