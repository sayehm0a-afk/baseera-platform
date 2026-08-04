"""Phase 2C: Market Risk and Exit Warning Engine.

A market-wide (not per-symbol) risk classification, deliberately kept
separate from `market_status.MarketSessionStatus` (which answers "is
the exchange open right now," a calendar/clock question) -- this module
answers a different question: "given the real breadth of today's scan
results, how permissive should new entries be right now." The two are
combined, not merged: a closed market always reports MARKET_CLOSED
here regardless of breadth, and an open market with too few scanned
symbols to be statistically meaningful honestly reports
INSUFFICIENT_DATA rather than guessing.

Breadth input (`MarketBreadthSummary`) comes from a real, already-
persisted `MarketScanRun` -- the buy/sell counts and average confidence
across every symbol scanned in the most recent completed run, read via
one cheap SQL aggregate (`MarketIntelligenceRepository.get_market_breadth`).
No index/TASI-level feed exists in this codebase (see
`src.backtesting.regime`'s own disclosed gap) -- breadth-of-scan-results
is the real, honestly-labeled substitute used throughout this
codebase's market-wide signals, not a fabricated index value.

The 9 states (Product Owner's exact naming) are ordered from most to
least permissive of new entries:

    STRONG_ENTRY        دخول قوي              -- entries encouraged
    SELECTIVE_ENTRY      دخول انتقائي          -- entries permitted, selectively
    NEUTRAL              محايد                 -- no strong signal either way
    CAUTION               حذر                  -- entries permitted but flagged
    REDUCE_POSITIONS      تخفيف مراكز           -- new entries blocked (existing positions: reduce)
    PARTIAL_EXIT          خروج جزئي             -- new entries blocked
    DEFENSIVE_EXIT         خروج دفاعي            -- new entries blocked, most defensive
    MARKET_CLOSED          السوق مغلق            -- session is not open; see last_session fields
    INSUFFICIENT_DATA       البيانات غير كافية    -- not enough scanned symbols to classify

Only REDUCE_POSITIONS/PARTIAL_EXIT/DEFENSIVE_EXIT are "entry-blocking"
(see `entry_permitted`) -- CAUTION still permits an entry, just with a
disclosed warning, matching how gates.py's other non-fatal gates work
(warn, don't silently block, unless the evidence is genuinely bad
enough to matter).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.market_intelligence.types import MarketBreadthSummary


class MarketRiskState(str, Enum):
    STRONG_ENTRY = "STRONG_ENTRY"
    SELECTIVE_ENTRY = "SELECTIVE_ENTRY"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    REDUCE_POSITIONS = "REDUCE_POSITIONS"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    DEFENSIVE_EXIT = "DEFENSIVE_EXIT"
    MARKET_CLOSED = "MARKET_CLOSED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


MARKET_RISK_LABELS_AR = {
    MarketRiskState.STRONG_ENTRY: "دخول قوي",
    MarketRiskState.SELECTIVE_ENTRY: "دخول انتقائي",
    MarketRiskState.NEUTRAL: "محايد",
    MarketRiskState.CAUTION: "حذر",
    MarketRiskState.REDUCE_POSITIONS: "تخفيف مراكز",
    MarketRiskState.PARTIAL_EXIT: "خروج جزئي",
    MarketRiskState.DEFENSIVE_EXIT: "خروج دفاعي",
    MarketRiskState.MARKET_CLOSED: "السوق مغلق",
    MarketRiskState.INSUFFICIENT_DATA: "البيانات غير كافية",
}

# Entry-blocking states: a new BUY-type decision is downgraded to WATCH
# when the live market risk state (not a stale last-session one -- see
# `classify_market_risk`) is one of these.
_ENTRY_BLOCKING_STATES = frozenset(
    {MarketRiskState.REDUCE_POSITIONS, MarketRiskState.PARTIAL_EXIT, MarketRiskState.DEFENSIVE_EXIT}
)

# Minimum symbols_scanned for the breadth-derived bands below to be
# treated as statistically meaningful rather than noise from a handful
# of symbols.
_MINIMUM_SYMBOLS_FOR_CLASSIFICATION = 15

# Buy-ratio bands (buy_count / (buy_count + sell_count)), most
# permissive first. A market with zero buy+sell signals (all HOLD) is
# treated as NEUTRAL (ratio undefined -> defaults to 0.5).
_STRONG_ENTRY_MIN_RATIO = 0.65
_STRONG_ENTRY_MIN_CONFIDENCE = 65.0
_SELECTIVE_ENTRY_MIN_RATIO = 0.55
_NEUTRAL_MIN_RATIO = 0.45
_CAUTION_MIN_RATIO = 0.35
_REDUCE_POSITIONS_MIN_RATIO = 0.25
_PARTIAL_EXIT_MIN_RATIO = 0.15


@dataclass(frozen=True)
class MarketRiskAssessment:
    state: MarketRiskState
    label_ar: str
    basis_ar: str
    """Arabic sentence tracing the classification to the real evidence
    used -- never a generic AI filler sentence."""
    entry_permitted: bool
    is_live: bool
    """False when this assessment reflects the last completed session
    (market currently closed) rather than a live, in-session read."""
    buy_count: Optional[int] = None
    sell_count: Optional[int] = None
    symbols_scanned: Optional[int] = None
    average_confidence: Optional[float] = None


def _insufficient_data(reason_ar: str) -> MarketRiskAssessment:
    return MarketRiskAssessment(
        state=MarketRiskState.INSUFFICIENT_DATA,
        label_ar=MARKET_RISK_LABELS_AR[MarketRiskState.INSUFFICIENT_DATA],
        basis_ar=reason_ar,
        entry_permitted=True,  # insufficient data must never itself block an entry
        is_live=False,
    )


def _classify_breadth(breadth: MarketBreadthSummary) -> MarketRiskState:
    denom = breadth.buy_count + breadth.sell_count
    buy_ratio = (breadth.buy_count / denom) if denom > 0 else 0.5
    confidence = breadth.average_confidence or 0.0

    if buy_ratio >= _STRONG_ENTRY_MIN_RATIO and confidence >= _STRONG_ENTRY_MIN_CONFIDENCE:
        return MarketRiskState.STRONG_ENTRY
    if buy_ratio >= _SELECTIVE_ENTRY_MIN_RATIO:
        return MarketRiskState.SELECTIVE_ENTRY
    if buy_ratio >= _NEUTRAL_MIN_RATIO:
        return MarketRiskState.NEUTRAL
    if buy_ratio >= _CAUTION_MIN_RATIO:
        return MarketRiskState.CAUTION
    if buy_ratio >= _REDUCE_POSITIONS_MIN_RATIO:
        return MarketRiskState.REDUCE_POSITIONS
    if buy_ratio >= _PARTIAL_EXIT_MIN_RATIO:
        return MarketRiskState.PARTIAL_EXIT
    return MarketRiskState.DEFENSIVE_EXIT


def _basis_ar(breadth: MarketBreadthSummary, buy_ratio_pct: float) -> str:
    return (
        f"نسبة الإشارات الإيجابية {buy_ratio_pct:.0f}% "
        f"({breadth.buy_count} شراء مقابل {breadth.sell_count} بيع) "
        f"من أصل {breadth.symbols_scanned} سهمًا تم فحصها في آخر عملية مسح، "
        f"بمتوسط ثقة {breadth.average_confidence:.0f}/100."
        if breadth.average_confidence is not None
        else (
            f"نسبة الإشارات الإيجابية {buy_ratio_pct:.0f}% "
            f"({breadth.buy_count} شراء مقابل {breadth.sell_count} بيع) "
            f"من أصل {breadth.symbols_scanned} سهمًا تم فحصها في آخر عملية مسح."
        )
    )


def classify_market_risk(
    *,
    market_is_open: bool,
    breadth: Optional[MarketBreadthSummary],
) -> MarketRiskAssessment:
    """Pure function. `breadth` is the most recent completed scan run's
    breadth (live if the market is open, last-session if it is not --
    the caller decides which run to fetch; this function only decides
    how to label and gate it).

    Precedence, most certain fact first: market-closed (a calendar
    fact, never ambiguous) beats breadth classification, which beats
    "no breadth data at all" (insufficient data)."""
    if not market_is_open:
        if breadth is None:
            return MarketRiskAssessment(
                state=MarketRiskState.MARKET_CLOSED,
                label_ar=MARKET_RISK_LABELS_AR[MarketRiskState.MARKET_CLOSED],
                basis_ar="السوق مغلق حاليًا، ولا تتوفر بيانات مسح سابقة لعرض آخر تصنيف للمخاطر.",
                entry_permitted=True,
                is_live=False,
            )
        if breadth.symbols_scanned < _MINIMUM_SYMBOLS_FOR_CLASSIFICATION:
            return MarketRiskAssessment(
                state=MarketRiskState.MARKET_CLOSED,
                label_ar=MARKET_RISK_LABELS_AR[MarketRiskState.MARKET_CLOSED],
                basis_ar=(
                    "السوق مغلق حاليًا. عدد الأسهم في آخر عملية مسح "
                    f"({breadth.symbols_scanned}) غير كافٍ لعرض تصنيف موثوق للجلسة السابقة."
                ),
                entry_permitted=True,
                is_live=False,
            )
        last_session_state = _classify_breadth(breadth)
        denom = breadth.buy_count + breadth.sell_count
        buy_ratio_pct = 100.0 * ((breadth.buy_count / denom) if denom > 0 else 0.5)
        return MarketRiskAssessment(
            state=MarketRiskState.MARKET_CLOSED,
            label_ar=MARKET_RISK_LABELS_AR[MarketRiskState.MARKET_CLOSED],
            basis_ar=(
                f"السوق مغلق حاليًا. تصنيف الجلسة السابقة كان "
                f"«{MARKET_RISK_LABELS_AR[last_session_state]}» — {_basis_ar(breadth, buy_ratio_pct)}"
            ),
            entry_permitted=True,
            is_live=False,
            buy_count=breadth.buy_count,
            sell_count=breadth.sell_count,
            symbols_scanned=breadth.symbols_scanned,
            average_confidence=breadth.average_confidence,
        )

    if breadth is None:
        return _insufficient_data("لا تتوفر بيانات مسح حديثة لتصنيف حالة مخاطر السوق حاليًا.")
    if breadth.symbols_scanned < _MINIMUM_SYMBOLS_FOR_CLASSIFICATION:
        return _insufficient_data(
            f"عدد الأسهم في آخر عملية مسح ({breadth.symbols_scanned}) "
            f"أقل من الحد الأدنى ({_MINIMUM_SYMBOLS_FOR_CLASSIFICATION}) لتصنيف موثوق لحالة السوق."
        )

    state = _classify_breadth(breadth)
    denom = breadth.buy_count + breadth.sell_count
    buy_ratio_pct = 100.0 * ((breadth.buy_count / denom) if denom > 0 else 0.5)
    return MarketRiskAssessment(
        state=state,
        label_ar=MARKET_RISK_LABELS_AR[state],
        basis_ar=_basis_ar(breadth, buy_ratio_pct),
        entry_permitted=state not in _ENTRY_BLOCKING_STATES,
        is_live=True,
        buy_count=breadth.buy_count,
        sell_count=breadth.sell_count,
        symbols_scanned=breadth.symbols_scanned,
        average_confidence=breadth.average_confidence,
    )
