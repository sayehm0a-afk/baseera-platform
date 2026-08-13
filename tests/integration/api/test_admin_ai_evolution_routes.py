"""Integration tests for /api/v1/admin/ai-evolution/* -- E9 of the AI
Evolution Layer. Real FastAPI routing against in-memory SQLite;
`get_current_user` is overridden per-test, the same technique
test_admin_routes.py already uses for staff-gated routes.
"""

from datetime import date, datetime, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user
from src.core.db.database import Base, get_db
from src.domain.models import (
    CalibrationConfig,
    CalibrationStatus,
    ConfidenceCalibrationMethod,
    ConfidenceCalibrationModel,
    ConfidenceCalibrationStatus,
    DailyIntelligenceSnapshot,
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    DiscoveredPattern,
    ReflectionReport,
    StaffRole,
    Stock,
    User,
    ValidationSession,
    ValidationSessionStatus,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    def _override_get_db():
        yield db

    main.app.dependency_overrides[get_db] = _override_get_db
    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def admin(session) -> User:
    u = User(email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def owner(session) -> User:
    u = User(email="owner@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def customer(session) -> User:
    u = User(email="customer@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


def _as(user: User) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture
def client(session) -> Iterator[TestClient]:
    yield TestClient(main.app)


def test_non_staff_customer_is_rejected_from_every_ai_evolution_route(client, customer):
    _as(customer)
    assert client.get("/api/v1/admin/ai-evolution/dashboard").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/calibration-status").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/patterns").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/reflections").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/paper-trade-comparison").status_code == 403


def test_dashboard_404s_when_no_snapshot_exists(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/dashboard")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "daily_intelligence_snapshot_not_found"


def test_dashboard_returns_the_most_recent_snapshot_by_default(client, admin, session):
    session.add(
        DailyIntelligenceSnapshot(
            snapshot_date=date(2026, 1, 1), recommendations_evaluated=10, successful_count=6, failed_count=4,
            partial_count=0, expired_count=0, win_rate=0.6, agent_panel_snapshot_count=0, agent_debate_count=0,
        )
    )
    session.add(
        DailyIntelligenceSnapshot(
            snapshot_date=date(2026, 1, 2), recommendations_evaluated=8, successful_count=3, failed_count=5,
            partial_count=0, expired_count=0, win_rate=0.375, agent_panel_snapshot_count=0, agent_debate_count=0,
        )
    )
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_date"] == "2026-01-02"
    # Non-negotiable: failed_count is always present, never suppressible.
    assert body["failed_count"] == 5
    assert body["successful_count"] == 3


def test_dashboard_accepts_an_explicit_date(client, admin, session):
    session.add(
        DailyIntelligenceSnapshot(
            snapshot_date=date(2026, 1, 1), recommendations_evaluated=10, successful_count=6, failed_count=4,
            partial_count=0, expired_count=0, win_rate=0.6, agent_panel_snapshot_count=0, agent_debate_count=0,
        )
    )
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/dashboard", params={"snapshot_date": "2026-01-01"})
    assert response.status_code == 200
    assert response.json()["snapshot_date"] == "2026-01-01"


def test_calibration_status_reports_null_fields_when_nothing_active(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/calibration-status")
    assert response.status_code == 200
    body = response.json()
    assert body["active_weight_calibration_version"] is None
    assert body["active_confidence_calibration_version"] is None
    assert body["latest_validated_challenger_version"] is None


def test_calibration_status_reports_active_and_challenger_configs(client, admin, session):
    session.add(CalibrationConfig(version="w-active", status=CalibrationStatus.ACTIVE, config={}, activated_at=datetime.now(timezone.utc)))
    session.add(CalibrationConfig(version="w-challenger", status=CalibrationStatus.VALIDATED, config={}))
    session.add(
        ConfidenceCalibrationModel(
            version="c-active", status=ConfidenceCalibrationStatus.ACTIVE, method=ConfidenceCalibrationMethod.PLATT,
            model_params={"coef": 1.0, "intercept": 0.0}, training_sample_size=50,
            activated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/calibration-status")
    assert response.status_code == 200
    body = response.json()
    assert body["active_weight_calibration_version"] == "w-active"
    assert body["active_confidence_calibration_version"] == "c-active"
    assert body["active_confidence_calibration_method"] == "PLATT"
    assert body["latest_validated_challenger_version"] == "w-challenger"


def test_list_patterns_defaults_to_every_pattern(client, admin, session):
    session.add(
        DiscoveredPattern(
            condition_type="signal_present", condition_description="RSI Oversold Crossover",
            evaluation_horizon_days=7, sample_size=40, win_rate=0.65, baseline_win_rate=0.5, z_score=2.1,
            p_value=0.03, still_valid=True, last_validated_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        DiscoveredPattern(
            condition_type="signal_present", condition_description="Stale Signal",
            evaluation_horizon_days=7, sample_size=35, win_rate=0.52, baseline_win_rate=0.5, z_score=0.2,
            p_value=0.8, still_valid=False, last_validated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/patterns")
    assert response.status_code == 200
    patterns = response.json()["patterns"]
    assert len(patterns) == 2

    still_valid_only = client.get("/api/v1/admin/ai-evolution/patterns", params={"still_valid": True})
    assert len(still_valid_only.json()["patterns"]) == 1
    assert still_valid_only.json()["patterns"][0]["condition_description"] == "RSI Oversold Crossover"


def test_list_reflections_returns_most_recent_first(client, admin, session):
    session.add(
        ReflectionReport(
            review_date=date(2026, 1, 1), recommendations_reviewed=5, successful_count=2, failed_count=3,
            partial_count=0, expired_count=0, win_rate=0.4, key_findings=["f1"], improvement_suggestions=[],
        )
    )
    session.add(
        ReflectionReport(
            review_date=date(2026, 1, 2), recommendations_reviewed=6, successful_count=4, failed_count=2,
            partial_count=0, expired_count=0, win_rate=0.667, key_findings=["f2"], improvement_suggestions=["s1"],
        )
    )
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/reflections")
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert len(reports) == 2
    assert reports[0]["review_date"] == "2026-01-02"
    # Non-negotiable: failed_count is always present.
    assert reports[0]["failed_count"] == 2
    assert reports[1]["failed_count"] == 3


def test_paper_trade_comparison_with_no_data(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/paper-trade-comparison")
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_horizon_days"] == 7
    assert body["champion_sample_size"] == 0
    assert body["significant"] is False


# --- GET /personal-performance (CONT Phase 3, OWNER-only) -------------------


def test_personal_performance_rejects_unauthenticated_requests(client):
    """No get_current_user override at all here -- a real request with
    no access_token cookie, exercising the actual 401 path."""
    response = client.get("/api/v1/admin/ai-evolution/personal-performance")
    assert response.status_code == 401


def test_personal_performance_rejects_admin_staff_who_is_not_owner(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/personal-performance")
    assert response.status_code == 403


def test_personal_performance_reports_insufficient_data_for_owner_with_no_history(client, owner):
    _as(owner)
    response = client.get("/api/v1/admin/ai-evolution/personal-performance")
    assert response.status_code == 200
    body = response.json()
    assert body["total_decisions_issued"] == 0
    assert body["insufficient_data_message_ar"] == "بيانات غير كافية لعرض هذا المقياس"
    assert body["market_risk_state_calibration_unavailable_ar"]


def test_personal_performance_reflects_real_decision_v2_distribution_for_owner(client, owner, session):
    stock = Stock(symbol="1111", name_en="Company 1111", sector="Energy")
    session.add(stock)
    session.commit()
    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id, symbol="1111", company_name_en="Company 1111", decision="BUY_CANDIDATE",
            decision_label_ar="شراء", confidence_score=75.0, opportunity_quality_score=70.0, risk_score=40.0,
            data_quality_score=90.0, data_freshness_status="LIVE", market_status="OPEN",
            decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="SAHMK_REAL",
            scan_run_id=1, entry_status="READY_NOW",
        )
    )
    session.commit()

    _as(owner)
    response = client.get("/api/v1/admin/ai-evolution/personal-performance")
    assert response.status_code == 200
    body = response.json()
    assert body["total_decisions_issued"] == 1
    assert body["decision_distribution"] == {"BUY_CANDIDATE": 1}
    assert body["entry_status_distribution"] == {"READY_NOW": 1}


# --- M10: /validation-sessions (OWNER for mutations, ADMIN for reads) ------


def test_non_staff_customer_is_rejected_from_every_validation_session_route(client, customer):
    _as(customer)
    assert client.post("/api/v1/admin/ai-evolution/validation-sessions", json={"name": "S1"}).status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/validation-sessions").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/validation-sessions/1").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/validation-sessions/1/metrics").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/validation-sessions/1/close").status_code == 403


def test_admin_cannot_create_or_close_a_validation_session(client, admin):
    """OWNER-only: an ADMIN can read validation-session data but must
    not be able to open or close the session that decides what counts
    as real M10 evidence."""
    _as(admin)
    assert client.post("/api/v1/admin/ai-evolution/validation-sessions", json={"name": "S1"}).status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/validation-sessions/1/close").status_code == 403


def test_owner_creates_a_validation_session(client, owner):
    _as(owner)
    response = client.post(
        "/api/v1/admin/ai-evolution/validation-sessions",
        json={"name": "M10 Session 1", "is_dry_run": True, "notes": "dry run before live"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "M10 Session 1"
    assert body["is_dry_run"] is True
    assert body["status"] == "RUNNING"
    assert body["created_by_user_id"] == owner.id


def test_owner_cannot_open_two_running_sessions_of_the_same_kind(client, owner):
    _as(owner)
    first = client.post("/api/v1/admin/ai-evolution/validation-sessions", json={"name": "S1", "is_dry_run": False})
    assert first.status_code == 201

    second = client.post("/api/v1/admin/ai-evolution/validation-sessions", json={"name": "S2", "is_dry_run": False})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "validation_session_conflict"


def test_owner_closes_a_validation_session(client, owner):
    _as(owner)
    created = client.post(
        "/api/v1/admin/ai-evolution/validation-sessions", json={"name": "S1", "is_dry_run": False}
    ).json()

    response = client.post(f"/api/v1/admin/ai-evolution/validation-sessions/{created['id']}/close")
    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"
    assert response.json()["ended_at"] is not None


def test_closing_an_already_closed_session_conflicts(client, owner):
    _as(owner)
    created = client.post(
        "/api/v1/admin/ai-evolution/validation-sessions", json={"name": "S1", "is_dry_run": False}
    ).json()
    client.post(f"/api/v1/admin/ai-evolution/validation-sessions/{created['id']}/close")

    second_close = client.post(f"/api/v1/admin/ai-evolution/validation-sessions/{created['id']}/close")
    assert second_close.status_code == 409


def test_get_validation_session_404s_when_missing(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/validation-sessions/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "validation_session_not_found"


def test_list_validation_sessions_filters_by_is_dry_run(client, owner, admin):
    _as(owner)
    client.post("/api/v1/admin/ai-evolution/validation-sessions", json={"name": "Real", "is_dry_run": False})
    client.post("/api/v1/admin/ai-evolution/validation-sessions", json={"name": "Dry", "is_dry_run": True})

    _as(admin)
    all_sessions = client.get("/api/v1/admin/ai-evolution/validation-sessions")
    assert len(all_sessions.json()["sessions"]) == 2

    dry_only = client.get("/api/v1/admin/ai-evolution/validation-sessions", params={"is_dry_run": True})
    assert len(dry_only.json()["sessions"]) == 1
    assert dry_only.json()["sessions"][0]["name"] == "Dry"


def test_validation_session_metrics_404s_when_session_missing(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/validation-sessions/999/metrics")
    assert response.status_code == 404


def test_validation_session_metrics_reflects_real_outcome_rows(client, admin, session):
    vs = ValidationSession(
        name="M10 Session", status=ValidationSessionStatus.RUNNING, is_dry_run=False,
        started_at=datetime.now(timezone.utc),
    )
    session.add(vs)
    session.commit()

    stock1 = Stock(symbol="1111", name_en="Company 1111", sector="Energy")
    stock2 = Stock(symbol="2222", name_en="Company 2222", sector="Materials")
    session.add_all([stock1, stock2])
    session.commit()

    snap1 = DecisionV2Snapshot(
        stock_id=stock1.id, symbol="1111", company_name_en="Company 1111", decision="BUY_CANDIDATE",
        decision_label_ar="شراء", confidence_score=80.0, opportunity_quality_score=70.0, risk_score=30.0,
        data_quality_score=90.0, data_freshness_status="LIVE", current_price=100.0, market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="SAHMK_REAL",
        validation_session_id=vs.id, ranking_position=1,
    )
    snap2 = DecisionV2Snapshot(
        stock_id=stock2.id, symbol="2222", company_name_en="Company 2222", decision="BUY_CANDIDATE",
        decision_label_ar="شراء", confidence_score=60.0, opportunity_quality_score=55.0, risk_score=40.0,
        data_quality_score=85.0, data_freshness_status="LIVE", current_price=50.0, market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="SAHMK_REAL",
        validation_session_id=vs.id, ranking_position=2,
    )
    session.add_all([snap1, snap2])
    session.flush()

    session.add(
        DecisionV2Outcome(
            decision_v2_snapshot_id=snap1.id, validation_session_id=vs.id, symbol="1111",
            due_at=datetime.now(timezone.utc), status=DecisionV2OutcomeStatus.TARGET_1_HIT,
            entry_price=100.0, return_pct=10.0,
        )
    )
    session.add(
        DecisionV2Outcome(
            decision_v2_snapshot_id=snap2.id, validation_session_id=vs.id, symbol="2222",
            due_at=datetime.now(timezone.utc), status=DecisionV2OutcomeStatus.STOP_LOSS_HIT,
            entry_price=50.0, return_pct=-8.0,
        )
    )
    session.commit()

    _as(admin)
    response = client.get(f"/api/v1/admin/ai-evolution/validation-sessions/{vs.id}/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["total_signals_issued"] == 2
    assert body["actionable_signals"] == 2
    assert body["win_rate"] == pytest.approx(0.5)
    assert body["stop_loss_rate"] == pytest.approx(0.5)
    # DATA_UNAVAILABLE must never be silently folded into win/loss.
    assert body["data_unavailable_count"] == 0

    ledger_response = client.get(f"/api/v1/admin/ai-evolution/validation-sessions/{vs.id}/ledger")
    assert ledger_response.status_code == 200
    ledger = ledger_response.json()
    assert ledger["validation_session_id"] == vs.id
    entries = {e["symbol"]: e for e in ledger["entries"]}
    assert set(entries) == {"1111", "2222"}
    assert entries["1111"]["ranking_position"] == 1
    assert entries["1111"]["outcome_status"] == "TARGET_1_HIT"
    assert entries["1111"]["return_pct"] == pytest.approx(10.0)
    assert entries["2222"]["outcome_status"] == "STOP_LOSS_HIT"
    assert entries["2222"]["return_pct"] == pytest.approx(-8.0)


def test_validation_session_ledger_404s_when_session_missing(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/validation-sessions/999/ledger")
    assert response.status_code == 404


def test_validation_session_ledger_includes_non_actionable_decisions_with_null_outcome(client, admin, session):
    vs = ValidationSession(
        name="M10 Session", status=ValidationSessionStatus.RUNNING, is_dry_run=False,
        started_at=datetime.now(timezone.utc),
    )
    session.add(vs)
    session.commit()

    stock = Stock(symbol="3333", name_en="Company 3333", sector="Retail")
    session.add(stock)
    session.commit()

    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id, symbol="3333", company_name_en="Company 3333", decision="WATCH",
            decision_label_ar="مراقبة", confidence_score=40.0, opportunity_quality_score=30.0, risk_score=50.0,
            data_quality_score=80.0, data_freshness_status="LIVE", current_price=20.0, market_status="OPEN",
            decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="SAHMK_REAL",
            validation_session_id=vs.id,
        )
    )
    session.commit()

    _as(admin)
    response = client.get(f"/api/v1/admin/ai-evolution/validation-sessions/{vs.id}/ledger")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["decision"] == "WATCH"
    assert entries[0]["outcome_status"] is None
