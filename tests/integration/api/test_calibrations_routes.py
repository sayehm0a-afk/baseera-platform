"""Integration tests for /api/v1/calibrations/* -- real FastAPI
routing, real CalibrationEngine, real BacktestingEngine runs during
/validate, in-memory SQLite. Same session_factory/get_db double-wiring
as test_backtests_routes.py -- /validate runs a real backtest
synchronously via CalibrationEngine, which needs Depends(get_db)'s
session, not a background job, so app.dependency_overrides alone is
sufficient for these routes (no database.get_session_factory
monkeypatch strictly required) -- kept anyway for consistency and in
case a future change adds a background path here too.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user
from src.core.db import database
from src.core.db.database import Base, get_db
from src.domain.models import CalibrationConfig, CalibrationStatus, PriceBar, StaffRole, Stock, Timeframe, User


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    # Every /api/v1/calibrations/* route is staff-only (Phase 10
    # M10.6) -- an in-memory staff user (never persisted;
    # get_current_user itself is overridden) satisfies
    # require_staff_role(...), keeping these tests focused on
    # calibration lifecycle behavior.
    staff_user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_current_user] = lambda: staff_user
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


def _seed_bars(session_factory, symbol="2222", count=300):
    session = session_factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    import random

    rng = random.Random(11)
    for i in range(count):
        price += rng.uniform(-0.3, 0.32)
        price = max(price, 5.0)
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(round(price, 4))), high=Decimal(str(round(price + 0.3, 4))),
                low=Decimal(str(round(price - 0.3, 4))), close=Decimal(str(round(price, 4))),
                volume=1000 + i, source="dev-synthetic", is_synthetic=True,
            )
        )
    session.commit()
    session.close()


_CREATE_REQUEST = {
    "config": {"recommendation_tuning": {"buy_threshold": 58.0}},
    "training_period_start": "2026-01-01",
    "training_period_end": "2026-04-01",
    "validation_period_start": "2026-04-02",
    "validation_period_end": "2026-06-01",
    "notes": "test candidate",
}


# --- create / list / get -------------------------------------------


def test_create_calibration_returns_a_draft(client, session_factory):
    response = client.post("/api/v1/calibrations", json=_CREATE_REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["config"] == _CREATE_REQUEST["config"]
    assert body["version"]


def test_create_calibration_rejects_invalid_periods(client, session_factory):
    bad = dict(_CREATE_REQUEST, validation_period_start="2026-06-01", validation_period_end="2026-04-02")
    response = client.post("/api/v1/calibrations", json=bad)
    assert response.status_code == 422


def test_list_calibrations(client, session_factory):
    client.post("/api/v1/calibrations", json=_CREATE_REQUEST)
    client.post("/api/v1/calibrations", json=_CREATE_REQUEST)
    response = client.get("/api/v1/calibrations")
    assert response.status_code == 200
    assert len(response.json()["calibrations"]) == 2


def test_get_calibration(client, session_factory):
    created = client.post("/api/v1/calibrations", json=_CREATE_REQUEST).json()
    response = client.get(f"/api/v1/calibrations/{created['version']}")
    assert response.status_code == 200
    assert response.json()["version"] == created["version"]


def test_get_calibration_404(client, session_factory):
    response = client.get("/api/v1/calibrations/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "calibration_not_found"


# --- validate ------------------------------------------------------


def test_validate_runs_a_real_backtest_and_records_a_verdict(client, session_factory):
    _seed_bars(session_factory)
    created = client.post("/api/v1/calibrations", json=_CREATE_REQUEST).json()

    response = client.post(
        f"/api/v1/calibrations/{created['version']}/validate",
        json={"symbols": ["2222"], "data_provenance_mode": "SYNTHETIC", "evaluation_frequency_days": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("VALIDATED", "REJECTED")
    assert body["metrics"] is not None
    assert body["baseline_comparison_metrics"] is not None
    assert body["notes"]


def test_validate_404_for_unknown_version(client, session_factory):
    response = client.post(
        "/api/v1/calibrations/does-not-exist/validate",
        json={"symbols": ["2222"], "data_provenance_mode": "SYNTHETIC"},
    )
    assert response.status_code == 404


def test_validate_a_second_time_is_rejected(client, session_factory):
    _seed_bars(session_factory)
    created = client.post("/api/v1/calibrations", json=_CREATE_REQUEST).json()
    request = {"symbols": ["2222"], "data_provenance_mode": "SYNTHETIC", "evaluation_frequency_days": 10}
    client.post(f"/api/v1/calibrations/{created['version']}/validate", json=request)

    response = client.post(f"/api/v1/calibrations/{created['version']}/validate", json=request)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_calibration_transition"


# --- activate / rollback ------------------------------------------------


def test_activate_requires_validated_status(client, session_factory):
    created = client.post("/api/v1/calibrations", json=_CREATE_REQUEST).json()  # still DRAFT
    response = client.post(f"/api/v1/calibrations/{created['version']}/activate")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_calibration_transition"


def test_activate_404_for_unknown_version(client, session_factory):
    response = client.post("/api/v1/calibrations/does-not-exist/activate")
    assert response.status_code == 404


def test_full_lifecycle_activate_then_rollback(client, session_factory):
    # Manually force a VALIDATED row (bypassing the real metrics comparison,
    # which is already covered by test_calibration_engine.py) to exercise
    # the REST-level activate/rollback transitions deterministically.
    session = session_factory()
    session.add(CalibrationConfig(version="v1", status=CalibrationStatus.VALIDATED, config={}))
    session.add(CalibrationConfig(version="v2", status=CalibrationStatus.VALIDATED, config={}))
    session.commit()
    session.close()

    activate1 = client.post("/api/v1/calibrations/v1/activate")
    assert activate1.status_code == 200
    assert activate1.json()["status"] == "ACTIVE"

    activate2 = client.post("/api/v1/calibrations/v2/activate")
    assert activate2.status_code == 200
    assert client.get("/api/v1/calibrations/v1").json()["status"] == "SUPERSEDED"

    rollback = client.post("/api/v1/calibrations/v1/rollback")
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "ACTIVE"
    assert client.get("/api/v1/calibrations/v2").json()["status"] == "ROLLED_BACK"


def test_rollback_404_for_unknown_version(client, session_factory):
    response = client.post("/api/v1/calibrations/does-not-exist/rollback")
    assert response.status_code == 404


def test_rollback_to_a_draft_version_is_rejected(client, session_factory):
    created = client.post("/api/v1/calibrations", json=_CREATE_REQUEST).json()  # DRAFT
    response = client.post(f"/api/v1/calibrations/{created['version']}/rollback")
    assert response.status_code == 409


# --- staff-only gating (Phase 10 M10.6) --------------------------------


def test_non_staff_user_is_rejected(client, session_factory):
    non_staff_user = User(email="customer@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff_user
    try:
        response = client.get("/api/v1/calibrations")
    finally:
        main.app.dependency_overrides[get_current_user] = (
            lambda: User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_permission"


# --- indicator-attribution ------------------------------------------------


def test_indicator_attribution_returns_all_eleven_indicators(client, session_factory):
    _seed_bars(session_factory)
    response = client.post(
        "/api/v1/calibrations/indicator-attribution",
        json={
            "symbols": ["2222"], "start_date": "2026-03-01", "end_date": "2026-08-01",
            "data_provenance_mode": "SYNTHETIC", "evaluation_frequency_days": 7, "holding_horizon_days": 20,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evaluated_count"] > 0
    assert set(body["directional_indicators"].keys()) == {
        "fibonacci", "support_resistance", "vwap", "volume_profile", "rsi", "macd", "adx", "ema", "sma",
    }
    assert set(body["risk_indicators"].keys()) == {"atr", "bollinger"}
    assert "win_rate" in body["directional_indicators"]["rsi"]


def test_indicator_attribution_rejects_invalid_date_range(client, session_factory):
    response = client.post(
        "/api/v1/calibrations/indicator-attribution",
        json={"symbols": ["2222"], "start_date": "2026-08-01", "end_date": "2026-03-01", "data_provenance_mode": "SYNTHETIC"},
    )
    assert response.status_code == 422


def test_indicator_attribution_staff_only(client, session_factory):
    non_staff_user = User(email="customer@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff_user
    try:
        response = client.post(
            "/api/v1/calibrations/indicator-attribution",
            json={"symbols": ["2222"], "start_date": "2026-03-01", "end_date": "2026-08-01"},
        )
    finally:
        main.app.dependency_overrides[get_current_user] = (
            lambda: User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
        )
    assert response.status_code == 403


# --- statistical-weights ---------------------------------------------------


def test_statistical_weights_returns_every_contributor(client, session_factory):
    _seed_bars(session_factory)
    response = client.post(
        "/api/v1/calibrations/statistical-weights",
        json={
            "symbols": ["2222"], "training_period_start": "2026-03-01", "training_period_end": "2026-09-01",
            "data_provenance_mode": "SYNTHETIC", "evaluation_frequency_days": 5, "holding_horizon_days": 15,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 11
    assert body["draft_calibration_version"] is None
    for entry in body["entries"]:
        assert entry["action"] in ("reweighted", "unchanged_insufficient_evidence", "unchanged_not_significant")


def test_statistical_weights_requires_validation_period_when_creating_a_draft(client, session_factory):
    response = client.post(
        "/api/v1/calibrations/statistical-weights",
        json={
            "symbols": ["2222"], "training_period_start": "2026-03-01", "training_period_end": "2026-09-01",
            "data_provenance_mode": "SYNTHETIC", "create_draft_calibration": True,
        },
    )
    assert response.status_code == 422


def test_statistical_weights_can_create_a_draft_calibration(client, session_factory):
    _seed_bars(session_factory)
    response = client.post(
        "/api/v1/calibrations/statistical-weights",
        json={
            "symbols": ["2222"], "training_period_start": "2026-03-01", "training_period_end": "2026-09-01",
            "data_provenance_mode": "SYNTHETIC", "evaluation_frequency_days": 5, "holding_horizon_days": 15,
            "create_draft_calibration": True,
            "validation_period_start": "2026-09-02", "validation_period_end": "2026-11-01",
        },
    )
    assert response.status_code == 200
    body = response.json()
    reweighted = [e for e in body["entries"] if e["action"] == "reweighted"]
    if reweighted:
        assert body["draft_calibration_version"] is not None
        draft = client.get(f"/api/v1/calibrations/{body['draft_calibration_version']}").json()
        assert draft["status"] == "DRAFT"
        assert draft["config"]["contributor_weights"]
    else:
        assert body["draft_calibration_version"] is None


def test_statistical_weights_staff_only(client, session_factory):
    non_staff_user = User(email="customer@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff_user
    try:
        response = client.post(
            "/api/v1/calibrations/statistical-weights",
            json={"symbols": ["2222"], "training_period_start": "2026-03-01", "training_period_end": "2026-09-01"},
        )
    finally:
        main.app.dependency_overrides[get_current_user] = (
            lambda: User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
        )
    assert response.status_code == 403
