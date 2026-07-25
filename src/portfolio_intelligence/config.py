"""Env-var configurable settings for the Autonomous Portfolio
Intelligence Layer -- matches src.market_intelligence.config's own
pattern (functions read the environment at call time, not at import
time, so tests can monkeypatch them per-test).
"""

import os


def get_max_holdings_per_portfolio() -> int:
    """A bounded-workload ceiling, same reasoning as
    MARKET_SCAN_MAX_SYMBOLS -- POST /portfolio/analyze runs
    synchronously (no background job, since a single portfolio's
    holdings count is inherently small), so this also bounds request
    latency."""
    return int(os.getenv("PORTFOLIO_MAX_HOLDINGS", "50"))


# --- concentration / diversification ---------------------------------------


def get_position_concentration_threshold() -> float:
    """A single position at or above this weight (0..1) is flagged as
    concentrated."""
    return float(os.getenv("PORTFOLIO_POSITION_CONCENTRATION_THRESHOLD", "0.25"))


def get_sector_concentration_threshold() -> float:
    return float(os.getenv("PORTFOLIO_SECTOR_CONCENTRATION_THRESHOLD", "0.40"))


# --- risk / volatility -------------------------------------------------------


def get_volatility_lookback_days() -> int:
    return int(os.getenv("PORTFOLIO_VOLATILITY_LOOKBACK_DAYS", "252"))


def get_min_overlapping_days_for_correlation() -> int:
    """A symbol with fewer than this many overlapping price-history
    days is excluded from the correlation matrix and volatility/
    drawdown estimate -- too little history to produce a meaningful
    statistic, disclosed rather than silently included."""
    return int(os.getenv("PORTFOLIO_MIN_OVERLAPPING_DAYS", "30"))


def get_trading_days_per_year() -> int:
    return int(os.getenv("PORTFOLIO_TRADING_DAYS_PER_YEAR", "252"))


def get_risk_score_high_volatility_threshold_pct() -> float:
    """Annualized volatility (%) at/above which the risk score treats
    a portfolio as high-risk on the volatility component."""
    return float(os.getenv("PORTFOLIO_RISK_HIGH_VOLATILITY_THRESHOLD_PCT", "35.0"))


# --- cash --------------------------------------------------------------------


def get_default_cash_target_pct_min() -> float:
    return float(os.getenv("PORTFOLIO_CASH_TARGET_PCT_MIN", "0.05"))


def get_default_cash_target_pct_max() -> float:
    return float(os.getenv("PORTFOLIO_CASH_TARGET_PCT_MAX", "0.15"))


def get_high_risk_cash_target_pct_max() -> float:
    """The recommended cash ceiling widens for a high/very-high-risk
    portfolio -- more dry powder recommended when holdings are
    volatile."""
    return float(os.getenv("PORTFOLIO_HIGH_RISK_CASH_TARGET_PCT_MAX", "0.25"))


# --- rebalancing ---------------------------------------------------------------


def get_overweight_drift_threshold() -> float:
    """A holding's weight this many percentage points (0..1 scale)
    above what its PositionSize band implies is flagged for REDUCE."""
    return float(os.getenv("PORTFOLIO_OVERWEIGHT_DRIFT_THRESHOLD", "0.10"))


def get_underweight_drift_threshold() -> float:
    return float(os.getenv("PORTFOLIO_UNDERWEIGHT_DRIFT_THRESHOLD", "0.05"))


def get_max_new_buy_opportunities() -> int:
    return int(os.getenv("PORTFOLIO_MAX_NEW_BUY_OPPORTUNITIES", "10"))


def get_target_weight_by_position_size() -> dict:
    """Default target portfolio weight (0..1) implied by each
    `PositionSize` band `AIDecisionEngine` already assigns a holding --
    a disclosed convention (not derived from any individual investor's
    risk tolerance), used only as the reference `PositionSizer`
    compares a holding's actual weight against."""
    return {
        "NONE": float(os.getenv("PORTFOLIO_TARGET_WEIGHT_NONE", "0.0")),
        "SMALL": float(os.getenv("PORTFOLIO_TARGET_WEIGHT_SMALL", "0.03")),
        "MODERATE": float(os.getenv("PORTFOLIO_TARGET_WEIGHT_MODERATE", "0.06")),
        "STANDARD": float(os.getenv("PORTFOLIO_TARGET_WEIGHT_STANDARD", "0.10")),
        "LARGE": float(os.getenv("PORTFOLIO_TARGET_WEIGHT_LARGE", "0.15")),
    }


# --- health score weights (must sum to 1.0) -----------------------------------


def get_health_score_weights() -> dict:
    return {
        "diversification": float(os.getenv("PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION", "0.30")),
        "risk": float(os.getenv("PORTFOLIO_HEALTH_WEIGHT_RISK", "0.30")),
        "cash_adequacy": float(os.getenv("PORTFOLIO_HEALTH_WEIGHT_CASH", "0.20")),
        "recommendation_alignment": float(os.getenv("PORTFOLIO_HEALTH_WEIGHT_ALIGNMENT", "0.20")),
    }
