"""RiskEngine: portfolio-level risk -- real correlation matrix and
volatility computed from already-ingested `PriceBar` history (via the
existing `load_price_bars` loader, reused unmodified), a drawdown
estimate from a reconstructed weighted equity curve, and a risk score
blending each holding's already-computed `RiskLevel`
(`AIDecisionEngine`, reused, never recomputed) with realized
volatility.

**Portfolio beta is architecture-ready, not wired to real data.**
`_compute_beta()` implements the standard covariance(returns, market) /
variance(market) formula and is exercised by unit tests with synthetic
series -- but this platform has not ingested any market/TASI index
price history (`MarketSnapshot`, this codebase's index-snapshot model,
remains unpopulated, the same disclosed gap Phases 6 and 7 already
note), so `portfolio_beta` is always `None` in practice, with
`beta_unavailable_reason` explaining exactly why. This mirrors the
`LLMAdapter`/`NullLLMAdapter` pattern from Phase 6: the mechanism is
built and proven, never fabricated against data that does not exist.
"""

import logging
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from src.analysis.decision.types import RiskLevel
from src.analysis.ohlcv_loader import load_price_bars
from src.domain.models import Stock, Timeframe
from src.portfolio_intelligence.config import (
    get_min_overlapping_days_for_correlation,
    get_risk_score_high_volatility_threshold_pct,
    get_trading_days_per_year,
    get_volatility_lookback_days,
)
from src.portfolio_intelligence.types import CorrelationMatrix, HoldingAnalysis, PortfolioRiskProfile

logger = logging.getLogger(__name__)

_RISK_LEVEL_ORDINAL = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.VERY_HIGH: 3}
_RISK_SCORE_HIGH_THRESHOLD = 75.0
_RISK_SCORE_MEDIUM_THRESHOLD = 50.0
_RISK_SCORE_LOW_THRESHOLD = 25.0

_BETA_UNAVAILABLE_REASON = (
    "No market/TASI index price history is ingested in this platform (MarketSnapshot, this codebase's "
    "index-snapshot model, remains unpopulated) -- portfolio beta cannot be computed against a live "
    "benchmark. The covariance/variance formula is implemented and unit-tested against synthetic data; "
    "wiring a real market index data source is future work, not part of this milestone."
)


def compute_beta(symbol_returns: pd.Series, market_returns: Optional[pd.Series]) -> Optional[float]:
    """The standard beta formula: cov(asset, market) / var(market).
    Returns `None` whenever no market series is supplied (always, in
    this codebase today) or there isn't enough overlapping data to
    compute a meaningful covariance."""
    if market_returns is None:
        return None
    aligned = pd.concat([symbol_returns, market_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return None
    covariance = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
    market_variance = aligned.iloc[:, 1].var()
    if market_variance is None or market_variance == 0:
        return None
    return float(covariance / market_variance)


class RiskEngine:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def compute(self, holdings: List[HoldingAnalysis]) -> PortfolioRiskProfile:
        available_holdings = [h for h in holdings if h.available and h.weight is not None]
        symbols = [h.symbol for h in available_holdings]

        session = self._session_factory()
        try:
            returns_by_symbol, excluded = self._load_returns(session, symbols)
        finally:
            session.close()

        weight_by_symbol = {h.symbol: h.weight for h in available_holdings}
        risk_level_by_symbol = {h.symbol: h.risk_level for h in available_holdings if h.risk_level is not None}

        volatility_pct, drawdown_pct, correlation_matrix = self._compute_volatility_and_drawdown(returns_by_symbol, weight_by_symbol)
        weighted_risk_level_score = self._weighted_risk_level_score(weight_by_symbol, risk_level_by_symbol)
        risk_score = self._risk_score(weighted_risk_level_score, volatility_pct)
        risk_level = self._risk_level_from_score(risk_score)

        narrative = self._narrative(risk_score, risk_level, volatility_pct, drawdown_pct, excluded)

        return PortfolioRiskProfile(
            risk_score=risk_score,
            risk_level=risk_level,
            expected_volatility_annualized_pct=volatility_pct,
            estimated_max_drawdown_pct=drawdown_pct,
            portfolio_beta=None,
            beta_unavailable_reason=_BETA_UNAVAILABLE_REASON,
            correlation_matrix=correlation_matrix,
            excluded_from_volatility=excluded,
            narrative=narrative,
        )

    @staticmethod
    def _load_returns(session: Session, symbols: List[str]) -> Tuple[Dict[str, pd.Series], List[str]]:
        lookback = get_volatility_lookback_days()
        min_days = get_min_overlapping_days_for_correlation()
        returns: Dict[str, pd.Series] = {}
        excluded: List[str] = []

        for symbol in symbols:
            stock = session.query(Stock).filter(Stock.symbol == symbol).one_or_none()
            if stock is None:
                excluded.append(symbol)
                continue
            df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)
            if df.empty:
                excluded.append(symbol)
                continue
            closes = df["close"].tail(lookback + 1)
            symbol_returns = closes.pct_change().dropna()
            if len(symbol_returns) < min_days:
                excluded.append(symbol)
                continue
            returns[symbol] = symbol_returns

        return returns, excluded

    @staticmethod
    def _compute_volatility_and_drawdown(
        returns_by_symbol: Dict[str, pd.Series], weight_by_symbol: Dict[str, float]
    ) -> Tuple[Optional[float], Optional[float], Optional[CorrelationMatrix]]:
        if not returns_by_symbol:
            return None, None, None

        trading_days = get_trading_days_per_year()
        symbols = list(returns_by_symbol.keys())
        returns_df = pd.DataFrame(returns_by_symbol)

        volatilities = {s: float(returns_df[s].std() * np.sqrt(trading_days)) for s in symbols}
        corr_df = returns_df[symbols].corr().fillna(0.0)

        weights = np.array([weight_by_symbol.get(s, 0.0) for s in symbols])
        vol_vector = np.array([volatilities[s] for s in symbols])
        covariance_matrix = np.outer(vol_vector, vol_vector) * corr_df.values
        portfolio_variance = float(weights @ covariance_matrix @ weights)
        portfolio_volatility_pct = round(float(np.sqrt(max(portfolio_variance, 0.0))) * 100.0, 4)

        weight_sum = weights.sum()
        normalized_weights = weights / weight_sum if weight_sum > 0 else weights
        portfolio_daily_returns = returns_df[symbols].fillna(0.0).dot(normalized_weights)
        equity_curve = (1.0 + portfolio_daily_returns).cumprod()
        running_max = equity_curve.cummax()
        drawdown_series = equity_curve / running_max - 1.0
        max_drawdown_pct = round(abs(float(drawdown_series.min())) * 100.0, 4) if not drawdown_series.empty else None

        matrix = {
            row_symbol: {col_symbol: round(float(corr_df.loc[row_symbol, col_symbol]), 4) for col_symbol in symbols}
            for row_symbol in symbols
        }
        correlation_matrix = CorrelationMatrix(
            symbols=symbols, matrix=matrix, lookback_days=get_volatility_lookback_days(), excluded_symbols=[],
        )

        return portfolio_volatility_pct, max_drawdown_pct, correlation_matrix

    @staticmethod
    def _weighted_risk_level_score(weight_by_symbol: Dict[str, float], risk_level_by_symbol: Dict[str, RiskLevel]) -> Optional[float]:
        if not risk_level_by_symbol:
            return None
        total_weight = sum(weight_by_symbol.get(s, 0.0) for s in risk_level_by_symbol)
        if total_weight <= 0:
            return None
        weighted_ordinal = sum(
            weight_by_symbol.get(s, 0.0) * _RISK_LEVEL_ORDINAL[level] for s, level in risk_level_by_symbol.items()
        )
        return (weighted_ordinal / total_weight) / 3.0 * 100.0

    @staticmethod
    def _risk_score(weighted_risk_level_score: Optional[float], volatility_pct: Optional[float]) -> float:
        volatility_component = None
        if volatility_pct is not None:
            volatility_component = min(100.0, volatility_pct / get_risk_score_high_volatility_threshold_pct() * 100.0)

        if weighted_risk_level_score is not None and volatility_component is not None:
            return round(0.5 * weighted_risk_level_score + 0.5 * volatility_component, 2)
        if weighted_risk_level_score is not None:
            return round(weighted_risk_level_score, 2)
        if volatility_component is not None:
            return round(volatility_component, 2)
        return 50.0  # no risk information available at all -- a neutral, conservative default, never LOW

    @staticmethod
    def _risk_level_from_score(risk_score: float) -> RiskLevel:
        if risk_score >= _RISK_SCORE_HIGH_THRESHOLD:
            return RiskLevel.VERY_HIGH
        if risk_score >= _RISK_SCORE_MEDIUM_THRESHOLD:
            return RiskLevel.HIGH
        if risk_score >= _RISK_SCORE_LOW_THRESHOLD:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _narrative(
        risk_score: float, risk_level: RiskLevel, volatility_pct: Optional[float],
        drawdown_pct: Optional[float], excluded: List[str],
    ) -> str:
        parts = [f"Portfolio risk score is {risk_score:.1f}/100 ({risk_level.value.replace('_', ' ').title()})."]
        if volatility_pct is not None:
            parts.append(f"Estimated annualized volatility is {volatility_pct:.1f}%.")
        else:
            parts.append("Volatility could not be estimated -- insufficient price history across holdings.")
        if drawdown_pct is not None:
            parts.append(f"Estimated maximum historical drawdown (at current weights) is {drawdown_pct:.1f}%.")
        if excluded:
            parts.append(f"Excluded from the volatility/correlation estimate (insufficient price history): {', '.join(excluded)}.")
        return " ".join(parts)
