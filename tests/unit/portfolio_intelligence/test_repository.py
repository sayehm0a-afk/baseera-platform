"""Repository tests for PortfolioRepository -- real SQLAlchemy ORM
against an in-memory SQLite DB, no mocking of the persistence layer
itself."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import Stock
from src.portfolio_intelligence.repository import PortfolioRepository, serialize_portfolio_analysis
from src.portfolio_intelligence.types import Holding, PortfolioAnalysis
from tests.unit.portfolio_intelligence._fixtures import make_holding_analysis


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def repo():
    return PortfolioRepository()


def test_create_and_get_portfolio(session, repo):
    portfolio = repo.create_portfolio(session, name="My Portfolio", cash_balance=1000.0)
    assert portfolio.id is not None
    reloaded = repo.get_portfolio(session, portfolio.id)
    assert reloaded.name == "My Portfolio"
    assert float(reloaded.cash_balance) == 1000.0


def test_get_portfolio_returns_none_for_unknown_id(session, repo):
    assert repo.get_portfolio(session, 9999) is None


def test_list_portfolios(session, repo):
    repo.create_portfolio(session, "A", 0)
    repo.create_portfolio(session, "B", 0)
    total, rows = repo.list_portfolios(session, limit=50, offset=0)
    assert total == 2
    assert len(rows) == 2


def test_update_cash_balance(session, repo):
    portfolio = repo.create_portfolio(session, "A", 100.0)
    repo.update_cash_balance(session, portfolio.id, 500.0)
    reloaded = repo.get_portfolio(session, portfolio.id)
    assert float(reloaded.cash_balance) == 500.0


def test_replace_holdings_creates_stock_rows_and_holdings(session, repo):
    portfolio = repo.create_portfolio(session, "A", 0)
    repo.replace_holdings(session, portfolio.id, [Holding(symbol="2222", quantity=10, average_cost=30.0)])

    holdings = repo.get_holdings(session, portfolio.id)
    assert len(holdings) == 1
    assert holdings[0].symbol == "2222"
    assert holdings[0].quantity == 10.0
    assert holdings[0].average_cost == 30.0

    stock = session.query(Stock).filter_by(symbol="2222").one()
    assert stock is not None


def test_replace_holdings_is_a_full_replace_not_an_upsert(session, repo):
    portfolio = repo.create_portfolio(session, "A", 0)
    repo.replace_holdings(session, portfolio.id, [Holding(symbol="2222", quantity=10)])
    repo.replace_holdings(session, portfolio.id, [Holding(symbol="1010", quantity=5)])

    holdings = repo.get_holdings(session, portfolio.id)
    assert [h.symbol for h in holdings] == ["1010"]


def test_replace_holdings_reuses_existing_stock_row(session, repo):
    session.add(Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy"))
    session.commit()
    portfolio = repo.create_portfolio(session, "A", 0)

    repo.replace_holdings(session, portfolio.id, [Holding(symbol="2222", quantity=10)])

    assert session.query(Stock).filter_by(symbol="2222").count() == 1


def _fake_analysis(portfolio_id: int) -> PortfolioAnalysis:
    from src.portfolio_intelligence.allocation_engine import AllocationEngine
    from src.portfolio_intelligence.cash_manager import CashManager
    from src.portfolio_intelligence.diversification_engine import DiversificationEngine
    from src.portfolio_intelligence.optimization_engine import OptimizationEngine
    from src.portfolio_intelligence.portfolio_score import PortfolioScore
    from src.portfolio_intelligence.recommendation_builder import RecommendationBuilder
    from src.analysis.decision.types import RiskLevel
    from src.portfolio_intelligence.types import PortfolioRiskProfile

    holdings = [make_holding_analysis(symbol="2222", weight=0.9)]
    allocation = AllocationEngine().compute(holdings, cash=100.0)
    diversification, concentration = DiversificationEngine().compute(holdings, [])
    risk_profile = PortfolioRiskProfile(
        risk_score=30.0, risk_level=RiskLevel.LOW, expected_volatility_annualized_pct=12.0,
        estimated_max_drawdown_pct=8.0, portfolio_beta=None, beta_unavailable_reason="n/a",
        correlation_matrix=None, excluded_from_volatility=[], narrative="risk narrative",
    )
    cash_recommendation = CashManager().recommend(allocation, risk_profile)
    from src.portfolio_intelligence.types import RebalancePlan

    rebalance_plan = RebalancePlan(actions=[], new_buy_opportunities=[], generated_at=datetime.now(timezone.utc), new_buy_opportunities_source="test")
    optimization_recommendations = OptimizationEngine().build(concentration, diversification, risk_profile, cash_recommendation, rebalance_plan)
    recommendations = RecommendationBuilder().build(rebalance_plan, cash_recommendation, optimization_recommendations)
    health_score = PortfolioScore().compute(diversification, risk_profile, cash_recommendation, holdings)

    return PortfolioAnalysis(
        portfolio_id=portfolio_id, name="Test", holdings=holdings, cash=100.0, total_value=allocation.total_value,
        allocation=allocation, sector_exposure=[], concentration=concentration, diversification=diversification,
        risk_profile=risk_profile, recommendations=recommendations, health_score=health_score,
        generated_at=datetime.now(timezone.utc),
    )


def test_save_and_read_back_analysis_snapshot(session, repo):
    portfolio = repo.create_portfolio(session, "A", 100.0)
    analysis = _fake_analysis(portfolio.id)

    snapshot = repo.save_analysis_snapshot(session, portfolio.id, analysis, engine_version="1.0.0")
    assert snapshot.id is not None
    assert float(snapshot.health_score) == analysis.health_score.score

    reloaded = repo.get_latest_analysis_snapshot(session, portfolio.id)
    assert reloaded.id == snapshot.id
    assert reloaded.analysis_json["portfolio_id"] == portfolio.id


def test_get_latest_analysis_snapshot_returns_the_most_recent(session, repo):
    portfolio = repo.create_portfolio(session, "A", 100.0)
    analysis = _fake_analysis(portfolio.id)
    repo.save_analysis_snapshot(session, portfolio.id, analysis, engine_version="1.0.0")
    second = repo.save_analysis_snapshot(session, portfolio.id, analysis, engine_version="1.0.0")

    latest = repo.get_latest_analysis_snapshot(session, portfolio.id)
    assert latest.id == second.id


def test_get_latest_analysis_snapshot_none_when_never_analyzed(session, repo):
    portfolio = repo.create_portfolio(session, "A", 100.0)
    assert repo.get_latest_analysis_snapshot(session, portfolio.id) is None


def test_serialize_portfolio_analysis_is_json_safe(session, repo):
    import json

    analysis = _fake_analysis(1)
    blob = serialize_portfolio_analysis(analysis)

    def _reject(o):
        raise TypeError(f"not serializable: {type(o)}")

    json.dumps(blob, default=_reject)
