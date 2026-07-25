"""Unit tests for RiskEngine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.decision.types import RiskLevel
from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.portfolio_intelligence.risk_engine import RiskEngine, compute_beta
from tests.unit.portfolio_intelligence._fixtures import make_decision, make_holding_analysis


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


def _seed_bars(factory, symbol, count=300, seed=1):
    import random

    session = factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    rng = random.Random(seed)
    for i in range(count):
        price += rng.uniform(-0.4, 0.45)
        price = max(price, 5.0)
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(round(price, 4))), high=Decimal(str(round(price + 0.3, 4))),
                low=Decimal(str(round(price - 0.3, 4))), close=Decimal(str(round(price, 4))), volume=1000 + i,
            )
        )
    session.commit()
    session.close()


def test_compute_returns_none_volatility_when_no_holdings_available(factory):
    profile = RiskEngine(factory).compute([make_holding_analysis(symbol="A", unavailable=True)])
    assert profile.expected_volatility_annualized_pct is None
    assert profile.estimated_max_drawdown_pct is None
    assert profile.correlation_matrix is None


def test_compute_produces_real_volatility_and_correlation(factory):
    _seed_bars(factory, "2222", seed=1)
    _seed_bars(factory, "1010", seed=2)
    holdings = [
        make_holding_analysis(symbol="2222", weight=0.6, decision=make_decision(symbol="2222", risk_level=RiskLevel.LOW)),
        make_holding_analysis(symbol="1010", weight=0.4, decision=make_decision(symbol="1010", risk_level=RiskLevel.HIGH)),
    ]
    profile = RiskEngine(factory).compute(holdings)

    assert profile.expected_volatility_annualized_pct is not None
    assert profile.expected_volatility_annualized_pct > 0
    assert profile.estimated_max_drawdown_pct is not None
    assert profile.estimated_max_drawdown_pct >= 0
    assert profile.correlation_matrix is not None
    assert set(profile.correlation_matrix.symbols) == {"2222", "1010"}
    assert profile.correlation_matrix.matrix["2222"]["2222"] == 1.0
    # every numeric field must be a plain Python float, never numpy.float64 (JSON/Pydantic safety)
    assert type(profile.expected_volatility_annualized_pct) is float
    assert type(profile.estimated_max_drawdown_pct) is float
    assert type(profile.risk_score) is float


def test_symbol_with_insufficient_history_is_excluded(factory, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_MIN_OVERLAPPING_DAYS", "30")
    _seed_bars(factory, "2222", count=5, seed=1)  # far below min_days
    holdings = [make_holding_analysis(symbol="2222", weight=1.0)]
    profile = RiskEngine(factory).compute(holdings)
    assert "2222" in profile.excluded_from_volatility
    assert profile.expected_volatility_annualized_pct is None


def test_beta_is_always_none_with_a_disclosed_reason(factory):
    _seed_bars(factory, "2222", seed=1)
    holdings = [make_holding_analysis(symbol="2222", weight=1.0)]
    profile = RiskEngine(factory).compute(holdings)
    assert profile.portfolio_beta is None
    assert "market/TASI index" in profile.beta_unavailable_reason


def test_risk_level_bands_from_risk_score(factory):
    _seed_bars(factory, "2222", seed=1)
    high_risk_holdings = [make_holding_analysis(symbol="2222", weight=1.0, decision=make_decision(symbol="2222", risk_level=RiskLevel.VERY_HIGH))]
    profile = RiskEngine(factory).compute(high_risk_holdings)
    assert profile.risk_score > 0


def test_compute_beta_formula_with_synthetic_series():
    asset_returns = pd.Series([0.01, 0.02, -0.01, 0.03, -0.02, 0.015])
    market_returns = pd.Series([0.008, 0.018, -0.008, 0.028, -0.018, 0.012])
    beta = compute_beta(asset_returns, market_returns)
    assert beta is not None
    assert beta > 0  # positively correlated synthetic series


def test_compute_beta_returns_none_when_no_market_series():
    asset_returns = pd.Series([0.01, 0.02, -0.01])
    assert compute_beta(asset_returns, None) is None


def test_compute_beta_returns_none_with_insufficient_overlap():
    asset_returns = pd.Series([0.01], index=[0])
    market_returns = pd.Series([0.01], index=[1])  # no overlapping index
    assert compute_beta(asset_returns, market_returns) is None
