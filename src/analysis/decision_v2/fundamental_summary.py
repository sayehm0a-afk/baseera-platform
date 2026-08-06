"""Section 12: a real, structured fundamental summary for Decision
Engine V2 -- revenue trend, profit trend, margins, debt, ROE, EPS
growth, valuation, and dividend yield.

Reads exclusively from `FundamentalAnalysisResult`'s already-computed
ratio properties (the same M2.3 output `fundamental_contributor.py`
already consumes for scoring) -- never recomputes a ratio, never
touches raw `FundamentalSnapshot` rows directly. Any ratio the engine
could not compute from real reported financials (a normal, disclosed
outcome -- see `RatioOutput`'s own docstring) stays `None` here too;
this module never fabricates a number to fill a gap. There is
deliberately no "cash flow" field: the M2.3 ratio registry has no
cash-flow-trend ratio today (only the point-in-time `cash_ratio`
liquidity measure), and inventing one here would violate the same
honesty rule the rest of Decision Engine V2 follows.
"""

from typing import Any, Dict, Optional, Tuple

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult

_NOT_AVAILABLE_AR = "البيانات المالية الأساسية غير متوفرة لهذا السهم حاليًا."


def _trend_ar(growth: Optional[float], subject_ar: str) -> str:
    if growth is None:
        return f"اتجاه {subject_ar} غير متاح (بيانات مالية سابقة غير كافية)."
    if growth > 0.05:
        return f"{subject_ar} في اتجاه تصاعدي واضح ({growth:+.1%})."
    if growth < -0.05:
        return f"{subject_ar} في اتجاه تراجعي ({growth:+.1%})."
    return f"{subject_ar} شبه مستقر ({growth:+.1%})."


def _valuation_ar(pe: Optional[float], pb: Optional[float]) -> str:
    if pe is None and pb is None:
        return "لا تتوفر بيانات كافية لتقييم مضاعفات السعر حاليًا."
    parts = []
    if pe is not None:
        parts.append(f"مكرر الربحية {pe:.1f}x")
    if pb is not None:
        parts.append(f"مكرر القيمة الدفترية {pb:.1f}x")
    return "التقييم الحالي: " + "، ".join(parts) + "."


def build_fundamental_summary(
    fundamental_result: Optional[FundamentalAnalysisResult],
) -> Tuple[Dict[str, Any], str]:
    """Returns (summary dict, one-sentence Arabic overview). The dict's
    keys are always present (never a fabricated value, but a stable
    shape for API/DB consumers): revenue_growth, profit_growth,
    net_profit_margin, gross_profit_margin, return_on_equity,
    debt_to_equity, price_to_earnings, price_to_book, dividend_yield,
    eps_growth -- each `None` when the underlying ratio could not be
    computed from real reported financials."""
    if fundamental_result is None:
        empty = {
            "revenue_growth": None, "profit_growth": None,
            "net_profit_margin": None, "gross_profit_margin": None,
            "return_on_equity": None, "debt_to_equity": None,
            "price_to_earnings": None, "price_to_book": None,
            "dividend_yield": None, "eps_growth": None,
        }
        return empty, _NOT_AVAILABLE_AR

    summary = {
        "revenue_growth": fundamental_result.revenue_growth,
        "profit_growth": fundamental_result.net_income_growth,
        "net_profit_margin": fundamental_result.net_profit_margin,
        "gross_profit_margin": fundamental_result.gross_profit_margin,
        "return_on_equity": fundamental_result.return_on_equity,
        "debt_to_equity": fundamental_result.debt_to_equity,
        "price_to_earnings": fundamental_result.price_to_earnings,
        "price_to_book": fundamental_result.price_to_book,
        "dividend_yield": fundamental_result.dividend_yield,
        "eps_growth": fundamental_result.eps_growth,
    }

    revenue_sentence = _trend_ar(summary["revenue_growth"], "الإيرادات")
    profit_sentence = _trend_ar(summary["profit_growth"], "الأرباح")
    valuation_sentence = _valuation_ar(summary["price_to_earnings"], summary["price_to_book"])
    overview = f"{revenue_sentence} {profit_sentence} {valuation_sentence}"
    return summary, overview
