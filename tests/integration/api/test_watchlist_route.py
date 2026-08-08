"""Integration tests for GET/POST/DELETE /api/v1/watchlist -- the
authenticated user's own personal watchlist.

Reuses the shared db_session/client fixtures from conftest.py; adds a
local `as_user` fixture that persists a real User row (needed since
UserWatchlist.user_id is a real foreign key, unlike authenticated_as_
staff's unpersisted in-memory User).
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import DecisionV2Snapshot, Stock, User, UserWatchlist, UserWatchlistItem


@pytest.fixture
def as_user(db_session):
    user = User(email="user@example.com", password_hash="hashed", is_staff=False)
    db_session.add(user)
    db_session.commit()
    main.app.dependency_overrides[get_current_user] = lambda: user
    yield user


@pytest.fixture
def other_user(db_session):
    user = User(email="other@example.com", password_hash="hashed", is_staff=False)
    db_session.add(user)
    db_session.commit()
    return user


def _make_stock(db_session, symbol="2222", name_ar="أرامكو السعودية", sector="الطاقة"):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", name_ar=name_ar, sector=sector)
    db_session.add(stock)
    db_session.commit()
    return stock


def _add_decision_v2(db_session, symbol, decision="BUY", confidence=75.0):
    stock = db_session.query(Stock).filter(Stock.symbol == symbol).one()
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=symbol,
        company_name_en=f"Stock {symbol}",
        company_name_ar=stock.name_ar,
        sector_ar=stock.sector,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=Decimal(str(confidence)),
        opportunity_quality_score=Decimal("60"),
        risk_score=Decimal("40"),
        data_quality_score=Decimal("90"),
        data_freshness_status="LIVE",
        current_price=Decimal("30.5"),
        entry_zone_low=Decimal("30.0"),
        entry_zone_high=Decimal("30.6"),
        stop_loss=Decimal("29.0"),
        target_1=Decimal("32.0"),
        target_2=Decimal("33.0"),
        target_3=Decimal("34.0"),
        market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0",
        data_source="SAHMK_REAL",
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


# --- authentication ---------------------------------------------------


def test_get_watchlist_requires_authentication(client, db_session):
    response = client.get("/api/v1/watchlist")
    assert response.status_code == 401


def test_add_watchlist_item_requires_authentication(client, db_session):
    response = client.post("/api/v1/watchlist/items", json={"symbol": "2222"})
    assert response.status_code == 401


# --- GET ----------------------------------------------------------------


def test_get_watchlist_is_empty_for_a_new_user(client, db_session, as_user):
    response = client.get("/api/v1/watchlist")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_get_watchlist_lazily_creates_exactly_one_watchlist(client, db_session, as_user):
    client.get("/api/v1/watchlist")
    client.get("/api/v1/watchlist")

    watchlists = db_session.query(UserWatchlist).filter_by(user_id=as_user.id).all()
    assert len(watchlists) == 1


# --- POST /items ----------------------------------------------------------


def test_add_item_succeeds_for_a_real_stock(client, db_session, as_user):
    _make_stock(db_session, "2222")

    response = client.post("/api/v1/watchlist/items", json={"symbol": "2222"})

    assert response.status_code == 201
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["company_name_ar"] == "أرامكو السعودية"
    assert body["latest_decision"] is None  # no snapshot exists yet -- must not be fabricated

    watchlist = db_session.query(UserWatchlist).filter_by(user_id=as_user.id).one()
    items = db_session.query(UserWatchlistItem).filter_by(watchlist_id=watchlist.id).all()
    assert len(items) == 1
    assert items[0].symbol == "2222"


def test_add_item_includes_the_real_latest_decision_v2_snapshot(client, db_session, as_user):
    _make_stock(db_session, "2222")
    _add_decision_v2(db_session, "2222", decision="BUY", confidence=82.5)

    response = client.post("/api/v1/watchlist/items", json={"symbol": "2222"})

    assert response.status_code == 201
    body = response.json()
    assert body["latest_decision"] == "BUY"
    assert body["latest_confidence_score"] == pytest.approx(82.5)
    assert body["latest_current_price"] == pytest.approx(30.5)
    assert body["latest_target_1"] == pytest.approx(32.0)
    assert body["latest_stop_loss"] == pytest.approx(29.0)


def test_add_item_rejects_an_unknown_symbol(client, db_session, as_user):
    response = client.post("/api/v1/watchlist/items", json={"symbol": "9999"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stock_not_found"


def test_add_item_rejects_a_malformed_symbol(client, db_session, as_user):
    response = client.post("/api/v1/watchlist/items", json={"symbol": "not-a-symbol"})
    assert response.status_code == 404


def test_add_item_rejects_a_duplicate(client, db_session, as_user):
    _make_stock(db_session, "2222")
    client.post("/api/v1/watchlist/items", json={"symbol": "2222"})

    response = client.post("/api/v1/watchlist/items", json={"symbol": "2222"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "watchlist_item_already_exists"

    watchlist = db_session.query(UserWatchlist).filter_by(user_id=as_user.id).one()
    items = db_session.query(UserWatchlistItem).filter_by(watchlist_id=watchlist.id).all()
    assert len(items) == 1


# --- DELETE /items/{symbol} -----------------------------------------------


def test_remove_item_succeeds(client, db_session, as_user):
    _make_stock(db_session, "2222")
    client.post("/api/v1/watchlist/items", json={"symbol": "2222"})

    response = client.delete("/api/v1/watchlist/items/2222")

    assert response.status_code == 200
    assert "message" in response.json()
    watchlist = db_session.query(UserWatchlist).filter_by(user_id=as_user.id).one()
    items = db_session.query(UserWatchlistItem).filter_by(watchlist_id=watchlist.id).all()
    assert items == []


def test_remove_item_404_when_not_present(client, db_session, as_user):
    response = client.delete("/api/v1/watchlist/items/2222")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "watchlist_item_not_found"


# --- IDOR / ownership regression tests ------------------------------------


def test_user_cannot_see_another_users_watchlist_items(client, db_session, as_user, other_user):
    _make_stock(db_session, "1120")
    other_watchlist = UserWatchlist(user_id=other_user.id, name="other")
    db_session.add(other_watchlist)
    db_session.commit()
    stock = db_session.query(Stock).filter_by(symbol="1120").one()
    db_session.add(UserWatchlistItem(watchlist_id=other_watchlist.id, stock_id=stock.id, symbol="1120"))
    db_session.commit()

    response = client.get("/api/v1/watchlist")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_user_cannot_remove_another_users_watchlist_item(client, db_session, as_user, other_user):
    _make_stock(db_session, "1120")
    other_watchlist = UserWatchlist(user_id=other_user.id, name="other")
    db_session.add(other_watchlist)
    db_session.commit()
    stock = db_session.query(Stock).filter_by(symbol="1120").one()
    db_session.add(UserWatchlistItem(watchlist_id=other_watchlist.id, stock_id=stock.id, symbol="1120"))
    db_session.commit()

    response = client.delete("/api/v1/watchlist/items/1120")

    assert response.status_code == 404  # not found in *this* user's watchlist -- never another's
    remaining = db_session.query(UserWatchlistItem).filter_by(watchlist_id=other_watchlist.id).all()
    assert len(remaining) == 1  # the other user's item was never touched
