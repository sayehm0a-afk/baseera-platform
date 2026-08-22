"""Integration tests for GET /api/v1/admin/historical-data-export/ohlcv --
the temporary, staff-only, read-only OHLCV export route built for the
DecisionEngineV2 historical validation harness (BASIRAH -- PHASE 3 REAL
HISTORICAL VALIDATION DATA ACCESS mandate).

The mandate's own words: "Before using it, prove that access control
prevents normal retail users from calling it." These tests are that
proof -- a real HTTP request through the real FastAPI app and RBAC
dependency chain, not an assertion in a docstring.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.api.dependencies import get_current_user
from src.domain.models import PriceBar, StaffRole, Stock, Timeframe, User

import main


@pytest.fixture
def admin_staff(db_session) -> User:
    """A persisted staff user (unlike `authenticated_as_staff`, which is
    deliberately never written to the DB) -- required here because the
    route calls `record_admin_action(actor_user_id=current_user.id)`,
    which needs a real foreign-key-able id."""
    user = User(email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    main.app.dependency_overrides[get_current_user] = lambda: user
    return user


def _seed_bars(session, symbol="1111", n=5):
    stock = Stock(symbol=symbol, name_en="Test Co", sector="Energy")
    session.add(stock)
    session.commit()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=start + timedelta(days=i),
                open=Decimal("100.0"),
                high=Decimal("101.0"),
                low=Decimal("99.0"),
                close=Decimal("100.5"),
                volume=1000,
                source="sahmk",
                is_synthetic=False,
            )
        )
    session.commit()
    return stock


def _params(symbols="1111", start="2026-01-01", end="2026-01-05"):
    return {"symbols": symbols, "start_date": start, "end_date": end}


def test_export_rejects_unauthenticated_caller(client, db_session):
    _seed_bars(db_session)
    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params=_params())
    assert response.status_code == 401
    assert "rows" not in response.text


def test_export_rejects_ordinary_retail_user(client, db_session):
    _seed_bars(db_session)
    retail_user = User(email="retail@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: retail_user

    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params=_params())
    assert response.status_code == 403
    assert "rows" not in response.text


def test_export_rejects_non_admin_staff_role(client, db_session):
    _seed_bars(db_session)
    support_staff = User(
        email="support@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.SUPPORT
    )
    main.app.dependency_overrides[get_current_user] = lambda: support_staff

    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params=_params())
    assert response.status_code == 403
    assert "rows" not in response.text


def test_export_rejects_analyst_staff_role(client, db_session):
    """Only ADMIN/OWNER may pull bulk historical data -- ANALYST is
    staff but is not in the route's allowed-role set."""
    _seed_bars(db_session)
    analyst = User(email="analyst@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ANALYST)
    main.app.dependency_overrides[get_current_user] = lambda: analyst

    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params=_params())
    assert response.status_code == 403


def test_export_allows_admin_and_returns_only_ohlcv_fields(client, db_session, admin_staff):
    _seed_bars(db_session)
    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params=_params())
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 5
    assert body["symbols_found"] == ["1111"]
    assert body["symbols_not_found"] == []
    assert body["truncated"] is False
    row = body["rows"][0]
    assert set(row.keys()) == {
        "symbol", "timestamp", "open", "high", "low", "close", "volume",
        "data_source", "is_synthetic", "corporate_action_adjustment",
    }
    assert row["corporate_action_adjustment"] is None


def test_export_requires_all_query_params(client, db_session, authenticated_as_staff):
    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params={"symbols": "1111"})
    assert response.status_code == 422


def test_export_rejects_empty_symbol_list(client, db_session, authenticated_as_staff):
    response = client.get(
        "/api/v1/admin/historical-data-export/ohlcv", params=_params(symbols="  ,  ")
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "no_symbols"


def test_export_rejects_inverted_date_range(client, db_session, authenticated_as_staff):
    response = client.get(
        "/api/v1/admin/historical-data-export/ohlcv",
        params=_params(start="2026-02-01", end="2026-01-01"),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "invalid_range"


def test_export_records_audit_log_entry(client, db_session, admin_staff):
    from src.domain.models import AuditLog

    _seed_bars(db_session)
    response = client.get("/api/v1/admin/historical-data-export/ohlcv", params=_params())
    assert response.status_code == 200

    entries = db_session.query(AuditLog).filter_by(action="historical_data_export.ohlcv").all()
    assert len(entries) == 1
    assert entries[0].actor_user_id == admin_staff.id
    assert entries[0].details_json["row_count"] == 5


def test_export_reports_symbols_not_found_without_erroring(client, db_session, admin_staff):
    _seed_bars(db_session, symbol="1111")
    response = client.get(
        "/api/v1/admin/historical-data-export/ohlcv", params=_params(symbols="1111,9999")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbols_found"] == ["1111"]
    assert body["symbols_not_found"] == ["9999"]
