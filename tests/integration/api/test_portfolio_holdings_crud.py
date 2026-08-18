"""Integration tests for the RADAR-C Phase H per-holding CRUD +
DB-only P&L + Decision V2 holder-guidance routes -- distinct from
test_portfolio_routes.py's POST /analyze + PortfolioAnalysisOut suite,
which requires a live market-data provider and a full multi-engine
analysis. Every route tested here is DB-only: no dependency on
get_market_provider at all (verified explicitly below).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user, get_market_provider
from src.core.db.database import Base, get_db
from src.domain.models import DecisionV2Snapshot, PriceBar, Stock, Timeframe, User
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.portfolio_intelligence.repository import PortfolioRepository
from src.subscriptions import subscription_service


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    current_user = User(email="phase-h-owner@example.com", password_hash="hashed", is_email_verified=True)
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


def _make_stock(session, symbol="2222", name_ar="أرامكو السعودية", sector="Energy") -> Stock:
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", name_ar=name_ar, sector=sector)
    session.add(stock)
    session.commit()
    return stock


def _add_bars(session, stock, prices):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, price in enumerate(prices):
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(price)), high=Decimal(str(price)), low=Decimal(str(price)),
                close=Decimal(str(price)), volume=1000,
            )
        )
    session.commit()


def _make_decision_snapshot(session, stock, decision="BUY_CANDIDATE", confidence="70"):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id, symbol=stock.symbol, company_name_en=stock.name_en, company_name_ar=stock.name_ar,
        sector_ar=stock.sector, decision=decision, decision_label_ar="x",
        confidence_score=Decimal(confidence), opportunity_quality_score=Decimal("60"),
        risk_score=Decimal("40"), data_quality_score=Decimal("90"), data_freshness_status="LIVE",
        current_price=Decimal("30.5"), market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0", data_source="SAHMK_REAL",
        decision_summary_ar="ملخص القرار", recommendation_basis="الأساس",
    )
    session.add(snapshot)
    session.commit()
    return snapshot


# --- portfolio lifecycle: list / create / delete -----------------------------


def test_list_my_portfolios_is_empty_before_any_are_created(client, db_session):
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    assert response.json()["portfolios"] == []


def test_create_portfolio_never_calls_the_market_data_provider(client, db_session):
    def _fail_if_called():
        raise AssertionError("POST /api/v1/portfolio must never resolve a live market-data provider")

    main.app.dependency_overrides[get_market_provider] = _fail_if_called
    response = client.post("/api/v1/portfolio", json={"name": "محفظتي", "cash_balance": 500.0})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "محفظتي"
    assert body["cash_balance"] == 500.0
    assert body["holdings_count"] == 0


def test_list_my_portfolios_reflects_created_ones_and_their_holdings_count(client, db_session):
    create_response = client.post("/api/v1/portfolio", json={"name": "P1"})
    portfolio_id = create_response.json()["id"]
    stock = _make_stock(db_session)
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10})

    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    portfolios = response.json()["portfolios"]
    assert len(portfolios) == 1
    assert portfolios[0]["id"] == portfolio_id
    assert portfolios[0]["holdings_count"] == 1


def test_list_my_portfolios_never_returns_another_users_portfolio(client, db_session):
    other_user = User(email="phase-h-other@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(other_user)
    db_session.commit()
    PortfolioRepository().create_portfolio(db_session, "Not Yours", 0.0, user_id=other_user.id)

    response = client.get("/api/v1/portfolio")
    assert response.json()["portfolios"] == []


def test_delete_portfolio_removes_it_and_its_holdings(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 5})

    response = client.delete(f"/api/v1/portfolio/{portfolio_id}")
    assert response.status_code == 200
    assert response.json()["message"]
    assert client.get("/api/v1/portfolio").json()["portfolios"] == []
    assert client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").status_code == 404


def test_delete_portfolio_404_for_another_users_portfolio(client, db_session):
    other_user = User(email="phase-h-del-other@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(other_user)
    db_session.commit()
    other = PortfolioRepository().create_portfolio(db_session, "Not Yours", 0.0, user_id=other_user.id)

    response = client.delete(f"/api/v1/portfolio/{other.id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


# --- holdings CRUD ------------------------------------------------------------


def test_get_holdings_on_a_freshly_created_portfolio_is_an_honest_empty_list(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P", "cash_balance": 1000.0}).json()["id"]
    response = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings")
    assert response.status_code == 200
    body = response.json()
    assert body["holdings"] == []
    assert body["total_invested_cost"] == 0
    assert body["total_current_value"] == 0
    assert body["total_value_with_cash"] == 1000.0


def test_add_holding_computes_real_pnl_from_persisted_price_bars(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session, symbol="2222", name_ar="أرامكو السعودية")
    _add_bars(db_session, stock, [30.0, 33.0])  # most recent close = 33.0

    response = client.post(
        f"/api/v1/portfolio/{portfolio_id}/holdings",
        json={"symbol": "2222", "quantity": 100, "average_cost": 30.0},
    )
    assert response.status_code == 201
    holding = response.json()
    assert holding["symbol"] == "2222"
    assert holding["name_ar"] == "أرامكو السعودية"
    assert holding["current_price"] == 33.0
    assert holding["invested_cost"] == 3000.0
    assert holding["current_value"] == 3300.0
    assert holding["unrealized_pnl"] == 300.0
    assert round(holding["unrealized_pnl_pct"], 2) == 10.0

    listed = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").json()
    assert listed["total_invested_cost"] == 3000.0
    assert listed["total_current_value"] == 3300.0
    assert listed["total_unrealized_pnl"] == 300.0


def test_add_holding_never_calls_the_market_data_provider(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, [30.0])

    def _fail_if_called():
        raise AssertionError("POST .../holdings must never resolve a live market-data provider")

    main.app.dependency_overrides[get_market_provider] = _fail_if_called
    response = client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 1})
    assert response.status_code == 201


def test_get_holdings_never_calls_the_market_data_provider(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, [30.0])
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 1})

    def _fail_if_called():
        raise AssertionError("GET .../holdings must never resolve a live market-data provider")

    main.app.dependency_overrides[get_market_provider] = _fail_if_called
    response = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings")
    assert response.status_code == 200


def test_holding_with_no_persisted_price_bar_shows_no_current_price_never_fabricated(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    _make_stock(db_session, symbol="9999")
    # No PriceBar rows added at all.

    response = client.post(
        f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": "9999", "quantity": 10, "average_cost": 5.0}
    )
    holding = response.json()
    assert holding["current_price"] is None
    assert holding["current_value"] is None
    assert holding["unrealized_pnl"] is None
    assert holding["freshness_label_ar"] == "غير معروف"
    assert holding["invested_cost"] == 50.0


def test_add_holding_rejects_a_duplicate_symbol_in_the_same_portfolio(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10})

    response = client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 5})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_holding"


def test_add_holding_404_for_another_users_portfolio(client, db_session):
    other_user = User(email="phase-h-add-other@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(other_user)
    db_session.commit()
    other = PortfolioRepository().create_portfolio(db_session, "Not Yours", 0.0, user_id=other_user.id)

    response = client.post(f"/api/v1/portfolio/{other.id}/holdings", json={"symbol": "2222", "quantity": 1})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


def test_update_holding_changes_quantity_and_average_cost(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, [40.0])
    holding_id = client.post(
        f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10, "average_cost": 30.0}
    ).json()["id"]

    response = client.patch(
        f"/api/v1/portfolio/{portfolio_id}/holdings/{holding_id}", json={"quantity": 20, "average_cost": 35.0}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 20.0
    assert body["average_cost"] == 35.0
    assert body["invested_cost"] == 700.0


def test_update_holding_404_for_an_unknown_holding_id(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    response = client.patch(f"/api/v1/portfolio/{portfolio_id}/holdings/9999", json={"quantity": 5})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_holding_not_found"


def test_update_holding_requires_at_least_one_field(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    holding_id = client.post(
        f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10}
    ).json()["id"]

    response = client.patch(f"/api/v1/portfolio/{portfolio_id}/holdings/{holding_id}", json={})
    assert response.status_code == 422


def test_delete_holding_removes_it_from_the_list(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    holding_id = client.post(
        f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10}
    ).json()["id"]

    response = client.delete(f"/api/v1/portfolio/{portfolio_id}/holdings/{holding_id}")
    assert response.status_code == 200
    assert response.json()["message"]
    assert client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").json()["holdings"] == []


def test_delete_holding_404_for_a_holding_in_a_different_portfolio(client, db_session):
    portfolio_a = client.post("/api/v1/portfolio", json={"name": "A"}).json()["id"]
    portfolio_b = client.post("/api/v1/portfolio", json={"name": "B"}).json()["id"]
    stock = _make_stock(db_session)
    holding_id = client.post(
        f"/api/v1/portfolio/{portfolio_a}/holdings", json={"symbol": stock.symbol, "quantity": 10}
    ).json()["id"]

    response = client.delete(f"/api/v1/portfolio/{portfolio_b}/holdings/{holding_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_holding_not_found"


# --- Decision V2 holder guidance ("already own -- what now") ----------------


@pytest.mark.parametrize(
    "engine_decision,expected_code,expected_label_ar",
    [
        ("STRONG_BUY_CANDIDATE", "HOLD", "احتفاظ"),
        ("BUY_CANDIDATE", "HOLD", "احتفاظ"),
        ("WATCH", "WATCH", "مراقبة"),
        ("WAIT_FOR_ENTRY", "WATCH", "مراقبة"),
        ("HOLD", "HOLD", "احتفاظ"),
        ("REDUCE", "REDUCE", "تخفيف"),
        ("EXIT", "EXIT", "خروج"),
        ("REJECT", "EXIT", "خروج"),
    ],
)
def test_holding_guidance_maps_decision_v2_onto_the_four_holder_options(
    client, db_session, engine_decision, expected_code, expected_label_ar
):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    _make_decision_snapshot(db_session, stock, decision=engine_decision)
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10})

    holding = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").json()["holdings"][0]
    assert holding["guidance_decision"] == expected_code
    assert holding["guidance_label_ar"] == expected_label_ar
    assert holding["guidance_confidence"] == 70.0


def test_holding_guidance_is_never_fabricated_when_the_engine_has_insufficient_data(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    _make_decision_snapshot(db_session, stock, decision="INSUFFICIENT_DATA")
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10})

    holding = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").json()["holdings"][0]
    assert holding["guidance_decision"] is None
    assert holding["guidance_label_ar"] is None


def test_holding_guidance_is_none_when_no_decision_v2_snapshot_exists_yet(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10})

    holding = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").json()["holdings"][0]
    assert holding["guidance_decision"] is None


def test_holding_guidance_uses_the_most_recent_of_multiple_decision_v2_snapshots(client, db_session):
    portfolio_id = client.post("/api/v1/portfolio", json={"name": "P"}).json()["id"]
    stock = _make_stock(db_session)
    older = _make_decision_snapshot(db_session, stock, decision="EXIT")
    older.decision_timestamp = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.commit()
    _make_decision_snapshot(db_session, stock, decision="HOLD")
    client.post(f"/api/v1/portfolio/{portfolio_id}/holdings", json={"symbol": stock.symbol, "quantity": 10})

    holding = client.get(f"/api/v1/portfolio/{portfolio_id}/holdings").json()["holdings"][0]
    assert holding["guidance_decision"] == "HOLD"
