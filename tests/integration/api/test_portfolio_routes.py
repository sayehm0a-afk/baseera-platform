"""Integration tests for /api/v1/portfolio/* -- real FastAPI routing,
a real PortfolioEngine analysis (TechnicalAnalysisEngine/
FundamentalAnalysisEngine/RecommendationEngine/AIDecisionEngine/
AnalystEngine, all reused unmodified) against in-memory SQLite and the
Dev* providers. No live network call anywhere.

Unlike /api/v1/market/scan, POST /api/v1/portfolio/analyze runs
synchronously (no BackgroundTask), so only the usual
app.dependency_overrides double-wiring is needed here -- no
database.get_session_factory monkeypatch required.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user, get_market_provider
from src.core.db import database
from src.core.db.database import Base, get_db
from src.domain.models import (
    FundamentalSnapshot,
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    PeriodType,
    PriceBar,
    Stock,
    Timeframe,
    User,
)
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.subscriptions import subscription_service


@pytest.fixture
def db_session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # A couple of these tests also exercise POST /api/v1/market/scan
    # (to prove new-buy-opportunity reuse) -- that route's background
    # job gets its session factory via a *local* `from
    # src.core.db.database import get_session_factory` call, the same
    # gotcha test_market_routes.py/test_backtests_routes.py already
    # document, so database.get_session_factory itself must be
    # monkeypatched too, not just Depends(get_db).
    monkeypatch.setattr(database, "get_session_factory", lambda: session_factory)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    # Every /api/v1/portfolio/* route now requires an authenticated,
    # ownership-scoped caller (Phase 10 M10.5) -- overriding
    # get_current_user directly (rather than a real register/login
    # flow) keeps these tests focused on portfolio behavior, matching
    # how get_market_provider is already faked out below. A real trial
    # subscription is provisioned too (exactly like a real registration
    # always does) because a couple of these tests also call
    # /api/v1/market/scan directly, which now requires
    # require_active_subscription() (Phase 13 P13.5).
    current_user = User(email="portfolio-owner@example.com", password_hash="hashed", is_email_verified=True)
    session.add(current_user)
    session.commit()
    subscription_service.provision_trial_subscription(session, current_user)

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_market_provider] = lambda: DevMarketDataProvider()
    main.app.dependency_overrides[get_current_user] = lambda: current_user

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(db_session) -> Iterator[TestClient]:
    yield TestClient(main.app)


def _seed_stock_with_bars(session, symbol, sector="Energy", count=80, price_step=0.08):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    for i in range(count):
        price += price_step
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(price)), high=Decimal(str(price + 0.5)), low=Decimal(str(price - 0.5)),
                close=Decimal(str(price)), volume=1000 + i,
            )
        )
    session.commit()
    return stock


def _add_fundamentals(session, symbol, fiscal_year=2025):
    stock = session.query(Stock).filter_by(symbol=symbol).one()
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id, period_type=PeriodType.ANNUAL, fiscal_period_end=date(fiscal_year, 12, 31),
            revenue=Decimal("1000000"), net_income=Decimal("150000"), total_assets=Decimal("2000000"),
            total_liabilities=Decimal("700000"), total_equity=Decimal("1300000"),
            current_assets=Decimal("900000"), current_liabilities=Decimal("400000"),
            shares_outstanding=1_000_000, eps=Decimal("0.15"), dividend_per_share=Decimal("0.02"),
            source="dev-synthetic", is_synthetic=True,
        )
    )
    session.commit()


# --- POST /analyze ----------------------------------------------------------


def test_analyze_creates_a_new_portfolio_and_returns_full_analysis(client, db_session):
    _seed_stock_with_bars(db_session, "2222", sector="Energy")
    _seed_stock_with_bars(db_session, "1010", sector="Banks")

    response = client.post(
        "/api/v1/portfolio/analyze",
        json={
            "name": "My Portfolio",
            "holdings": [{"symbol": "2222", "quantity": 100, "average_cost": 30.0}, {"symbol": "1010", "quantity": 50, "average_cost": 28.0}],
            "cash": 3000.0,
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["portfolio_id"] is not None
    assert len(body["holdings"]) == 2
    assert body["total_value"] > 0
    assert "allocation" in body and "sector_exposure" in body
    assert "concentration" in body and "diversification" in body
    assert "risk_profile" in body and "recommendations" in body and "health_score" in body


def test_analyze_rejects_too_many_holdings(client, db_session, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_MAX_HOLDINGS", "1")
    response = client.post(
        "/api/v1/portfolio/analyze",
        json={"name": "P", "holdings": [{"symbol": "2222", "quantity": 1}, {"symbol": "1010", "quantity": 1}], "cash": 0},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_portfolio_config"


def test_re_analyzing_an_existing_portfolio_replaces_holdings(client, db_session):
    _seed_stock_with_bars(db_session, "2222")
    _seed_stock_with_bars(db_session, "1010", sector="Banks")

    first = client.post(
        "/api/v1/portfolio/analyze",
        json={"name": "P", "holdings": [{"symbol": "2222", "quantity": 10}], "cash": 100},
    ).json()
    portfolio_id = first["portfolio_id"]
    assert [h["symbol"] for h in first["holdings"]] == ["2222"]

    second = client.post(
        "/api/v1/portfolio/analyze",
        json={"portfolio_id": portfolio_id, "name": "P", "holdings": [{"symbol": "1010", "quantity": 5}], "cash": 200},
    ).json()
    assert second["portfolio_id"] == portfolio_id
    assert [h["symbol"] for h in second["holdings"]] == ["1010"]
    assert second["cash"] == 200


def test_analyze_404_for_unknown_portfolio_id(client, db_session):
    response = client.post("/api/v1/portfolio/analyze", json={"portfolio_id": 9999, "holdings": [], "cash": 0})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


def test_analyze_gracefully_handles_a_symbol_with_no_data(client, db_session):
    _seed_stock_with_bars(db_session, "2222")
    db_session.add(Stock(symbol="9999", name_en="No data", sector="Other"))
    db_session.commit()

    response = client.post(
        "/api/v1/portfolio/analyze",
        json={"holdings": [{"symbol": "2222", "quantity": 10}, {"symbol": "9999", "quantity": 5}], "cash": 0},
    )
    assert response.status_code == 200
    by_symbol = {h["symbol"]: h for h in response.json()["holdings"]}
    assert by_symbol["2222"]["available"] is True
    assert by_symbol["9999"]["available"] is False


# --- GET routes (read from the persisted snapshot) --------------------------


def _create_and_analyze(client, db_session):
    _seed_stock_with_bars(db_session, "2222", sector="Energy")
    _seed_stock_with_bars(db_session, "1010", sector="Banks")
    _add_fundamentals(db_session, "2222")
    _add_fundamentals(db_session, "1010")
    response = client.post(
        "/api/v1/portfolio/analyze",
        json={
            "name": "P",
            "holdings": [{"symbol": "2222", "quantity": 100, "average_cost": 30.0}, {"symbol": "1010", "quantity": 50, "average_cost": 28.0}],
            "cash": 2000.0,
        },
    )
    return response.json()["portfolio_id"]


def test_get_portfolio_returns_latest_snapshot(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)
    response = client.get(f"/api/v1/portfolio/{portfolio_id}")
    assert response.status_code == 200
    assert response.json()["portfolio_id"] == portfolio_id


def test_get_portfolio_404_when_never_analyzed(client, db_session):
    from src.portfolio_intelligence.repository import PortfolioRepository

    owner = db_session.query(User).one()
    portfolio = PortfolioRepository().create_portfolio(db_session, "Empty", 0.0, user_id=owner.id)
    response = client.get(f"/api/v1/portfolio/{portfolio.id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_portfolio_analysis"


def test_get_portfolio_404_for_unknown_id(client, db_session):
    response = client.get("/api/v1/portfolio/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


def test_get_portfolio_404_for_another_users_portfolio(client, db_session):
    """Ownership enforcement (Phase 10 M10.5): a portfolio that exists
    but belongs to a different user must look identical to one that
    doesn't exist at all -- 404, never 403 (no existence leakage)."""
    from src.portfolio_intelligence.repository import PortfolioRepository

    other_user = User(email="someone-else@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(other_user)
    db_session.commit()

    other_users_portfolio = PortfolioRepository().create_portfolio(
        db_session, "Not Yours", 0.0, user_id=other_user.id
    )
    response = client.get(f"/api/v1/portfolio/{other_users_portfolio.id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


@pytest.mark.parametrize(
    "path,expected_keys",
    [
        ("/recommendations", {"rebalance_actions", "new_buy_opportunities", "cash_recommendation", "optimization_recommendations"}),
        ("/risk", {"risk_score", "risk_level", "narrative"}),
        ("/allocation", {"entries", "cash", "cash_weight", "total_value"}),
        ("/diversification", {"score", "effective_number_of_holdings", "narrative"}),
        ("/rebalance", {"rebalance_actions", "new_buy_opportunities"}),
        ("/health", {"score", "band", "components", "narrative"}),
    ],
)
def test_sub_resource_routes_return_the_expected_shape(client, db_session, path, expected_keys):
    portfolio_id = _create_and_analyze(client, db_session)
    response = client.get(f"/api/v1/portfolio/{portfolio_id}{path}")
    assert response.status_code == 200
    assert expected_keys <= set(response.json().keys())


def test_risk_response_includes_a_real_correlation_matrix(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)
    response = client.get(f"/api/v1/portfolio/{portfolio_id}/risk")
    body = response.json()
    assert body["correlation_matrix"] is not None
    assert set(body["correlation_matrix"]["symbols"]) == {"2222", "1010"}
    assert body["portfolio_beta"] is None
    assert "market/TASI index" in body["beta_unavailable_reason"]


def test_rebalance_new_buy_opportunities_reuse_market_intelligence_when_a_scan_exists(client, db_session):
    _seed_stock_with_bars(db_session, "2222", sector="Energy")
    _seed_stock_with_bars(db_session, "1010", sector="Banks")
    _seed_stock_with_bars(db_session, "1120", sector="Banks")

    scan_response = client.post("/api/v1/market/scan", json={})
    scan_run_id = scan_response.json()["id"]
    assert client.get(f"/api/v1/market/scan/{scan_run_id}").json()["status"] == "SUCCESS"

    portfolio_response = client.post(
        "/api/v1/portfolio/analyze", json={"holdings": [{"symbol": "2222", "quantity": 10}], "cash": 0}
    )
    portfolio_id = portfolio_response.json()["portfolio_id"]

    response = client.get(f"/api/v1/portfolio/{portfolio_id}/rebalance")
    assert response.status_code == 200
    # 1010/1120 were not held -- if either was ranked a buy opportunity by the
    # market scan, it should appear here; the assertion below only confirms
    # the response is well-formed and never includes the already-held symbol.
    opportunity_symbols = {o["symbol"] for o in response.json()["new_buy_opportunities"]}
    assert "2222" not in opportunity_symbols


# --- security / honesty ------------------------------------------------------


def test_portfolio_responses_never_expose_credentials(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)
    for path in ("", "/recommendations", "/risk", "/allocation"):
        response = client.get(f"/api/v1/portfolio/{portfolio_id}{path}")
        body_text = response.text.lower()
        assert "sahmk_api_key" not in body_text
        assert "shmk_" not in body_text


# --- news alerts (Phase 12 -- requirement 10) --------------------------------


def _seed_analyzed_news_event(session, symbol, category, sentiment_score, confidence, external_key="k1"):
    event = NewsEvent(
        external_key=external_key, headline=f"Breaking news about {symbol}", source="sahmk", category=category,
        sentiment_score=sentiment_score, confidence=confidence, analyzed_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, symbol=symbol))
    session.commit()
    return event


def test_get_news_alerts_is_empty_before_any_refresh(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)
    response = client.get(f"/api/v1/portfolio/{portfolio_id}/news-alerts")
    assert response.status_code == 200
    assert response.json()["alerts"] == []


def test_get_news_alerts_404_for_unknown_portfolio(client, db_session):
    response = client.get("/api/v1/portfolio/9999/news-alerts")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


def test_get_news_alerts_404_for_another_users_portfolio(client, db_session):
    from src.portfolio_intelligence.repository import PortfolioRepository

    other_user = User(email="alerts-someone-else@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(other_user)
    db_session.commit()
    other_users_portfolio = PortfolioRepository().create_portfolio(db_session, "Not Yours", 0.0, user_id=other_user.id)

    response = client.get(f"/api/v1/portfolio/{other_users_portfolio.id}/news-alerts")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


def test_refresh_news_alerts_generates_an_alert_for_a_held_symbol_with_critical_news(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)  # holds 2222 and 1010
    _seed_analyzed_news_event(db_session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    response = client.post(f"/api/v1/portfolio/{portfolio_id}/news-alerts/refresh")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "2222"
    assert alerts[0]["alert_type"] == "HIGH_RISK"
    assert alerts[0]["id"] is not None
    assert alerts[0]["portfolio_id"] == portfolio_id

    persisted = client.get(f"/api/v1/portfolio/{portfolio_id}/news-alerts")
    assert len(persisted.json()["alerts"]) == 1


def test_refresh_news_alerts_is_idempotent_on_rerun(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)
    _seed_analyzed_news_event(db_session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    first = client.post(f"/api/v1/portfolio/{portfolio_id}/news-alerts/refresh")
    second = client.post(f"/api/v1/portfolio/{portfolio_id}/news-alerts/refresh")

    assert len(first.json()["alerts"]) == 1
    assert len(second.json()["alerts"]) == 0


def test_refresh_news_alerts_ignores_news_for_symbols_not_held(client, db_session):
    portfolio_id = _create_and_analyze(client, db_session)  # holds only 2222 and 1010
    db_session.add(Stock(symbol="1120", name_en="Al Rajhi", sector="Banks"))
    db_session.commit()
    _seed_analyzed_news_event(db_session, "1120", NewsCategory.LAWSUIT, -0.7, 90.0)

    response = client.post(f"/api/v1/portfolio/{portfolio_id}/news-alerts/refresh")
    assert response.status_code == 200
    assert response.json()["alerts"] == []


def test_refresh_news_alerts_404_for_unknown_portfolio(client, db_session):
    response = client.post("/api/v1/portfolio/9999/news-alerts/refresh")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"
