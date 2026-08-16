"""Stage 1 of the two-stage Radar scan (SAHMK quota optimization
mandate, 2026-08-16): narrows the full eligible Saudi-market universe
down to a smaller set of genuine candidates using ONLY already-
persisted local data -- zero SAHMK requests, no matter how large the
universe is.

Reuses, rather than reimplements, everything that already exists:
`SymbolSelector` for universe resolution (same DB-only query the
scheduler itself uses), `load_price_bars` for OHLCV (DB-only),
`TechnicalAnalysisEngine` for every indicator (the same engine every
other decision path in this codebase already runs), and
`derive_support_resistance` for breakout detection (the same function
`decision_v2/evidence.py` already uses in the live decision pipeline).
The only genuinely new logic here is the local-only "current price/
volume" substitution: everywhere else in this codebase, "current"
price/volume comes from a live quote (`context.extra["quote"]`);
Stage 1 has no live quote by design, so it uses the most recent
already-ingested PriceBar's close/volume instead -- the same figures
the once-daily OHLCV sync (see market_data.ingestion.config) already
keeps fresh in the database.

Candidate selection is threshold-based, not a fixed top-N cut (per the
mandate: "Do not hard-code these numbers without evidence") -- a
symbol becomes a candidate when it passes a liquidity floor AND at
least one genuine local signal fires (abnormal volume, a trending ADX
reading, an RSI extreme, or a resistance breakout). The real number of
candidates a given day's universe produces is meant to be *measured*,
not decided in advance; see the admin GET .../stage1-scan route this
module backs for exactly that measurement.

Two of the four signal thresholds are reused verbatim from the
existing live decision pipeline, not invented here:
`ABNORMAL_VOLUME_RATIO` is the identical 2.0x bar
`decision_v2/evidence.py`'s `derive_accumulation_evidence` already
uses for "abnormal volume." The other two (`TRENDING_ADX_THRESHOLD`,
RSI extremes) are conventional technical-analysis thresholds, not yet
validated against this platform's own real forward-tested outcomes --
that validation is exactly what the existing outcome-tracking/
calibration infrastructure (src.ai_evolution, src.backtesting) would
need real accumulated data to confirm over time, disclosed here rather
than silently presented as tuned.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.analysis.decision_v2.evidence import derive_support_resistance
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.domain.models import Stock, Timeframe
from src.market_intelligence.symbol_selector import SymbolSelector

# Reused verbatim from src.analysis.decision_v2.evidence's own
# "abnormal volume" bar -- not a new number invented for Stage 1.
ABNORMAL_VOLUME_RATIO = 2.0

# A conventional ADX "trending" threshold (below ~20-25, a market is
# usually considered range-bound/non-trending) -- not yet forward-
# tested against this platform's own outcomes; see module docstring.
TRENDING_ADX_THRESHOLD = 25.0

RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0

# TechnicalAnalysisEngine.analyze()'s own minimum-rows requirement
# (MACD's 26+9 warm-up is the longest) -- a symbol with fewer bars than
# this cannot be scored at all, not a Stage-1-specific choice.
MIN_INDICATOR_ROWS = 35

# A conservative liquidity floor (last close * last volume, in SAR) so
# an illiquid/untradeable micro-cap doesn't become a "candidate" purely
# because one of its indicators crossed a threshold on thin volume.
# Not yet evidence-derived against this platform's own real trading
# outcomes -- disclosed, not hidden; see module docstring.
MIN_DOLLAR_VOLUME_SAR = 100_000.0


@dataclass(frozen=True)
class Stage1Signal:
    name: str
    detail_ar: str


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
    dollar_volume = latest_close * latest_volume

    sr_evidence = derive_support_resistance(latest_close, result.support_resistance)
    breakout = sr_evidence.breakout_level is not None and latest_close > sr_evidence.breakout_level

    signals: List[Stage1Signal] = []
    if relative_volume is not None and relative_volume >= ABNORMAL_VOLUME_RATIO:
        signals.append(
            Stage1Signal("abnormal_volume", f"حجم تداول أعلى من المعتاد ({relative_volume:.1f}x المتوسط)")
        )
    if adx is not None and adx >= TRENDING_ADX_THRESHOLD:
        signals.append(Stage1Signal("trending", f"اتجاه قوي (ADX = {adx:.1f})"))
    if rsi is not None and rsi <= RSI_OVERSOLD:
        signals.append(Stage1Signal("rsi_oversold", f"منطقة تشبع بيعي (RSI = {rsi:.1f})"))
    if rsi is not None and rsi >= RSI_OVERBOUGHT:
        signals.append(Stage1Signal("rsi_overbought", f"منطقة تشبع شرائي (RSI = {rsi:.1f})"))
    if breakout:
        signals.append(Stage1Signal("resistance_breakout", "اختراق أقرب مستوى مقاومة"))

    passes_liquidity = dollar_volume >= MIN_DOLLAR_VOLUME_SAR
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
    )


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
        key=lambda r: len(r.signals),
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
