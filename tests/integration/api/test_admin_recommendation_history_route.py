"""Integration tests for /api/v1/admin/recommendation-history -- the
staff-only audit view that extends the public history route with raw
internal fields (contributor_breakdown, signals, total_score,
calibration_version, run_id, source).
"""

from datetime import datetime, timedelta, timezone

from src.domain.models import RecommendationLabel, RecommendationSnapshot, StaffRole, Stock, User


def _seed_stock(session, symbol="2222"):
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _seed_snapshot(session, stock, symbol="2222"):
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=symbol,
        evaluated_at=datetime.now(timezone.utc) - timedelta(days=5),
        market_price_at_evaluation=30.0,
        recommendation=RecommendationLabel.BUY,
        total_score=70.0,
        confidence_score=72.5,
        target_price=33.0,
        stop_loss=28.0,
        engine_version="2.0.0",
        is_paper_trade=False,
        reasons=["مؤشرات فنية إيجابية"],
        contributor_breakdown=[{"source": "technical", "points": 12.5, "weight": 0.3}],
        signals=[{"name": "rsi_oversold", "value": True}],
        calibration_version="v1",
        source="live_scan",
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def test_admin_history_requires_staff_role(client, db_session):
    from src.api.dependencies import get_current_user
    import main

    ordinary_user = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: ordinary_user

    response = client.get("/api/v1/admin/recommendation-history")
    assert response.status_code == 403


def test_admin_history_includes_internal_fields_for_staff(client, db_session, authenticated_as_staff):
    stock = _seed_stock(db_session)
    _seed_snapshot(db_session, stock)

    response = client.get("/api/v1/admin/recommendation-history")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["symbol"] == "2222"
    assert item["contributor_breakdown"] == [{"source": "technical", "points": 12.5, "weight": 0.3}]
    assert item["signals"] == [{"name": "rsi_oversold", "value": True}]
    assert item["total_score"] == 70.0
    assert item["calibration_version"] == "v1"
    assert item["source"] == "live_scan"


def test_admin_history_excludes_paper_trades_same_as_the_public_route(client, db_session, authenticated_as_staff):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    snapshot.is_paper_trade = True
    db_session.commit()

    response = client.get("/api/v1/admin/recommendation-history")
    assert response.json()["total"] == 0


def test_admin_history_filters_by_symbol(client, db_session, authenticated_as_staff):
    stock_a = _seed_stock(db_session, "2222")
    stock_b = _seed_stock(db_session, "1120")
    _seed_snapshot(db_session, stock_a, "2222")
    _seed_snapshot(db_session, stock_b, "1120")

    response = client.get("/api/v1/admin/recommendation-history", params={"symbol": "1120"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "1120"


def test_admin_history_non_admin_staff_role_is_rejected(client, db_session):
    from src.api.dependencies import get_current_user
    import main

    support_staff = User(
        email="support@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.SUPPORT
    )
    main.app.dependency_overrides[get_current_user] = lambda: support_staff

    response = client.get("/api/v1/admin/recommendation-history")
    assert response.status_code == 403


def test_admin_history_is_accessible_to_an_analyst_account(client, db_session):
    from src.api.dependencies import get_current_user
    import main

    analyst = User(email="analyst@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ANALYST)
    main.app.dependency_overrides[get_current_user] = lambda: analyst

    stock = _seed_stock(db_session)
    _seed_snapshot(db_session, stock)

    response = client.get("/api/v1/admin/recommendation-history")
    assert response.status_code == 200
    assert response.json()["total"] == 1
