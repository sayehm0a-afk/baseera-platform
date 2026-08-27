"""Unit tests for RebalanceEngine -- including its reuse of Phase 7's
market_intelligence RankingEngine/repository for new-buy opportunities.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.decision.types import RiskLevel
from src.core.db.database import Base
from src.domain.models import MarketScanStatus, RecommendationLabel, Stock
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.portfolio_intelligence.rebalance_engine import RebalanceEngine
from src.portfolio_intelligence.types import PortfolioRiskProfile
from tests.unit.portfolio_intelligence._fixtures import make_decision, make_holding_analysis


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _risk_profile():
    return PortfolioRiskProfile(
        risk_score=50.0, risk_level=RiskLevel.MEDIUM, expected_volatility_annualized_pct=None,
        estimated_max_drawdown_pct=None, portfolio_beta=None, beta_unavailable_reason="n/a",
        correlation_matrix=None, excluded_from_volatility=[], narrative="",
    )


def test_plan_produces_one_action_per_available_holding(session):
    holdings = [
        make_holding_analysis(symbol="A", weight=0.1, decision=make_decision(symbol="A")),
        make_holding_analysis(symbol="B", unavailable=True),
    ]
    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])
    assert len(plan.actions) == 1
    assert plan.actions[0].symbol == "A"


def test_no_completed_scan_means_no_new_buy_opportunities(session):
    holdings = [make_holding_analysis(symbol="A", decision=make_decision(symbol="A"))]
    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])
    assert plan.new_buy_opportunities == []
    assert "POST /api/v1/market/scan" in plan.new_buy_opportunities_source


def _seed_market_scan(session, symbols_and_recommendations):
    repo = MarketIntelligenceRepository()
    run = repo.create_scan_run(session, symbols_requested=len(symbols_and_recommendations))
    repo.finish_run(session, run.id, MarketScanStatus.SUCCESS, symbols_succeeded=len(symbols_and_recommendations), symbols_skipped=0, symbols_failed=0)

    from src.domain.models import SymbolIntelligenceRecord

    for symbol, recommendation in symbols_and_recommendations:
        stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
        session.add(stock)
        session.commit()
        # Realistic price/target/stop so a BUY/STRONG_BUY fixture carries
        # a defensible trade setup (positive expected return, risk/reward
        # >= 1.0) -- publication_gate.py rejects a "recommendation" with no
        # priced target/stop the same way it would reject a real one, so
        # these values matter to whether the fixture is a real opportunity.
        # `position_size` must also be a real, non-NONE value: read_model.
        # outcome_from_record() defaults a missing position_size to
        # PositionSize.NONE (indistinguishable from a sizer that
        # genuinely found no viable position), which the
        # position_sizing publication gate now rejects.
        session.add(
            SymbolIntelligenceRecord(
                scan_run_id=run.id, stock_id=stock.id, symbol=symbol, sector="Energy",
                recommendation=RecommendationLabel(recommendation), confidence=Decimal("80.0"), final_score=Decimal("75.0"),
                latest_price=Decimal("100.0"), target_price=Decimal("110.0"), stop_loss=Decimal("95.0"),
                expected_return_pct=Decimal("10.0"), position_size="STANDARD",
                evaluated_at=datetime.now(timezone.utc), engine_version="1.0.0",
            )
        )
    session.commit()
    return run


def test_new_buy_opportunities_reuse_market_intelligence_rankings(session):
    _seed_market_scan(session, [("2222", "STRONG_BUY"), ("1010", "BUY"), ("1120", "HOLD")])
    holdings = [make_holding_analysis(symbol="9999", decision=make_decision(symbol="9999"))]  # not one of the scanned symbols

    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])

    symbols = {o.symbol for o in plan.new_buy_opportunities}
    assert "2222" in symbols
    assert "1010" in symbols
    assert "1120" not in symbols  # HOLD is not a buy opportunity
    assert plan.new_buy_opportunities_source.startswith("market_scan_run_")


def test_new_buy_opportunities_exclude_symbols_already_held(session):
    _seed_market_scan(session, [("2222", "STRONG_BUY")])
    holdings = [make_holding_analysis(symbol="2222", decision=make_decision(symbol="2222"))]  # already held

    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])

    assert plan.new_buy_opportunities == []


def test_new_buy_opportunities_never_selects_a_newer_shadow_run(session):
    """PR #105 independent audit: rebalance_engine.py's
    _find_new_buy_opportunities is the highest-severity of the three
    secondary call sites the leak fix touched -- it serves full
    opportunity data (symbols, targets, stops) via GET /api/v1/
    portfolio/{id}/rebalance, not just a breadth metadata field. A
    newer, Shadow-internal MarketScanRun (linked via
    RecurrentScanCycle.scan_run_id, exactly like
    RecurrentLiveScanScheduler creates) with a DIFFERENT BUY symbol
    must never be selected over the real, older consumer scan."""
    from src.domain.models import RecurrentScanCycle, RecurrentScanCycleStatus

    consumer_run = _seed_market_scan(session, [("2222", "STRONG_BUY")])
    shadow_run = _seed_market_scan(session, [("7777", "STRONG_BUY")])
    assert shadow_run.id > consumer_run.id

    session.add(RecurrentScanCycle(
        cycle_id="audit-rebalance-shadow-cycle", status=RecurrentScanCycleStatus.SUCCESS_NO_CHANGE,
        scan_run_id=shadow_run.id, triggered_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    ))
    session.commit()

    holdings = [make_holding_analysis(symbol="9999", decision=make_decision(symbol="9999"))]
    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])

    symbols = {o.symbol for o in plan.new_buy_opportunities}
    assert symbols == {"2222"}
    assert "7777" not in symbols
    assert plan.new_buy_opportunities_source == f"market_scan_run_{consumer_run.id}"


def test_new_buy_opportunities_shadow_only_returns_empty_not_shadow_data(session):
    """Case E for this call site: if the ONLY MarketScanRun that
    exists is Shadow-internal, the route's honest-empty-state contract
    (already proven by test_no_completed_scan_means_no_new_buy_
    opportunities above) must hold -- never a silent fallback to
    Shadow's real opportunity data."""
    from src.domain.models import RecurrentScanCycle, RecurrentScanCycleStatus

    shadow_run = _seed_market_scan(session, [("2222", "STRONG_BUY")])
    session.add(RecurrentScanCycle(
        cycle_id="audit-rebalance-shadow-only", status=RecurrentScanCycleStatus.SUCCESS_NO_CHANGE,
        scan_run_id=shadow_run.id, triggered_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    ))
    session.commit()

    holdings = [make_holding_analysis(symbol="9999", decision=make_decision(symbol="9999"))]
    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])

    assert plan.new_buy_opportunities == []
    assert "POST /api/v1/market/scan" in plan.new_buy_opportunities_source


def test_new_buy_opportunities_respects_max_count(session, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_MAX_NEW_BUY_OPPORTUNITIES", "1")
    _seed_market_scan(session, [("2222", "STRONG_BUY"), ("1010", "STRONG_BUY")])
    holdings = []

    plan = RebalanceEngine(session).plan(holdings, _risk_profile(), [])

    assert len(plan.new_buy_opportunities) == 1
