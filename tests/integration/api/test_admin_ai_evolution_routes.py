"""Integration tests for /api/v1/admin/ai-evolution/* -- E9 of the AI
Evolution Layer. Real FastAPI routing against in-memory SQLite;
`get_current_user` is overridden per-test, the same technique
test_admin_routes.py already uses for staff-gated routes.
"""

import random
from datetime import date, datetime, timedelta, timezone
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
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
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


def test_calibration_status_reports_the_decision_v2_source_separately(client, admin, session):
    """Regression test for a real production gap (2026-08-18 real-market
    validation audit): the route used to call get_active_model() with no
    `source` argument, defaulting to legacy_v1 -- it could never show
    whether Decision V2 / Radar V2's own confidence calibration model
    (training_source="decision_v2") is active, even when one is."""
    session.add(
        ConfidenceCalibrationModel(
            version="c-legacy-active", status=ConfidenceCalibrationStatus.ACTIVE,
            method=ConfidenceCalibrationMethod.PLATT, training_source="legacy_v1",
            model_params={"coef": 1.0, "intercept": 0.0}, training_sample_size=50,
            activated_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        ConfidenceCalibrationModel(
            version="c-decision-v2-active", status=ConfidenceCalibrationStatus.ACTIVE,
            method=ConfidenceCalibrationMethod.ISOTONIC, training_source="decision_v2",
            model_params={"x_thresholds": [0.0, 1.0], "y_thresholds": [0.0, 1.0]}, training_sample_size=1200,
            activated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/calibration-status")
    assert response.status_code == 200
    body = response.json()
    assert body["active_confidence_calibration_version"] == "c-legacy-active"
    assert body["active_confidence_calibration_method"] == "PLATT"
    assert body["active_decision_v2_confidence_calibration_version"] == "c-decision-v2-active"
    assert body["active_decision_v2_confidence_calibration_method"] == "ISOTONIC"


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


# --- POST/GET /confidence-calibrations/* ---------------------------
#
# Real ConfidenceCalibrationEngine end-to-end through the HTTP layer
# (no mocking) -- src.ai_evolution.confidence_calibration's own unit
# tests already cover the engine's internals (Platt/isotonic fitting,
# ECE math, lifecycle transitions) exhaustively; these tests only
# prove the new routes wire real requests/responses onto that engine
# correctly.


def _confidence_calibration_stock(session) -> Stock:
    stock = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _seed_confidence_outcome(session, stock, day_offset, confidence, success, horizon_days=7):
    evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    snapshot = RecommendationSnapshot(
        stock_id=stock.id, symbol=stock.symbol, evaluated_at=evaluated_at, market_price_at_evaluation=100.0,
        recommendation=RecommendationLabel.BUY, total_score=60.0, confidence_score=confidence,
        target_price=110.0, stop_loss=90.0, engine_version="1.0.0", source="live_scan",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        RecommendationOutcome(
            snapshot_id=snapshot.id, symbol=stock.symbol, evaluation_horizon_days=horizon_days,
            due_at=evaluated_at + timedelta(days=horizon_days),
            status=RecommendationOutcomeStatus.SUCCESSFUL if success else RecommendationOutcomeStatus.FAILED,
            evaluated_at=evaluated_at + timedelta(days=horizon_days),
        )
    )


def _seed_confidence_overconfident_dataset(session, stock, n=60, seed=42):
    """A systematically overconfident engine: stated confidence always
    ~85, true success rate ~50% -- a real Platt/isotonic fit must
    improve ECE (mirrors test_confidence_calibration.py's own
    dataset)."""
    rng = random.Random(seed)
    for i in range(n):
        _seed_confidence_outcome(session, stock, day_offset=i, confidence=85.0, success=rng.random() < 0.5)
    session.commit()


_PROPOSE_REQUEST = {"training_period_start": "2026-01-01", "training_period_end": "2026-12-31"}


def test_non_staff_customer_is_rejected_from_confidence_calibration_routes(client, customer):
    _as(customer)
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=_PROPOSE_REQUEST).status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/confidence-calibrations").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/confidence-calibrations/v1").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibrations/v1/test").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibrations/v1/activate").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibrations/v1/rollback").status_code == 403


def test_create_confidence_calibration_returns_a_draft(client, admin, session):
    stock = _confidence_calibration_stock(session)
    _seed_confidence_overconfident_dataset(session, stock, n=60)

    _as(admin)
    response = client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=_PROPOSE_REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["training_source"] == "legacy_v1"
    assert body["training_sample_size"] == 60
    assert body["calibration_error_before"] is not None
    assert body["calibration_error_after"] is not None
    assert body["version"]


def test_create_confidence_calibration_422s_below_minimum_sample_size(client, admin, session):
    stock = _confidence_calibration_stock(session)
    _seed_confidence_outcome(session, stock, day_offset=0, confidence=70.0, success=True)
    session.commit()

    _as(admin)
    response = client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=_PROPOSE_REQUEST)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_calibration_data"


def test_create_confidence_calibration_rejects_invalid_period(client, admin):
    _as(admin)
    bad = dict(_PROPOSE_REQUEST, training_period_start="2026-12-31", training_period_end="2026-01-01")
    response = client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=bad)
    assert response.status_code == 422


def test_list_confidence_calibrations_filters_by_source(client, admin, session):
    session.add(
        ConfidenceCalibrationModel(
            version="c-legacy", status=ConfidenceCalibrationStatus.DRAFT, method=ConfidenceCalibrationMethod.PLATT,
            training_source="legacy_v1", model_params={"coef": 1.0, "intercept": 0.0}, training_sample_size=50,
        )
    )
    session.add(
        ConfidenceCalibrationModel(
            version="c-v2", status=ConfidenceCalibrationStatus.DRAFT, method=ConfidenceCalibrationMethod.PLATT,
            training_source="decision_v2", model_params={"coef": 1.0, "intercept": 0.0}, training_sample_size=50,
        )
    )
    session.commit()

    _as(admin)
    all_response = client.get("/api/v1/admin/ai-evolution/confidence-calibrations")
    assert len(all_response.json()["models"]) == 2

    filtered = client.get("/api/v1/admin/ai-evolution/confidence-calibrations", params={"source": "decision_v2"})
    assert [m["version"] for m in filtered.json()["models"]] == ["c-v2"]


def test_get_confidence_calibration_404(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/ai-evolution/confidence-calibrations/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "confidence_calibration_not_found"


def test_confidence_calibration_full_lifecycle_via_http(client, admin, session):
    """propose -> test -> activate for a first model, then propose a
    second, test, activate (superseding the first), then roll back to
    the first -- entirely through the HTTP routes, against a real
    overconfident dataset that a genuine fit must improve. Proves
    /test moves an improving fit to VALIDATED (never auto-passes),
    /activate takes effect (visible on /calibration-status) and
    supersedes the prior active model, and /rollback can reactivate a
    specific earlier version."""
    stock = _confidence_calibration_stock(session)
    _seed_confidence_overconfident_dataset(session, stock, n=100, seed=1)

    _as(admin)
    first = client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=_PROPOSE_REQUEST).json()
    first_version = first["version"]

    tested = client.post(f"/api/v1/admin/ai-evolution/confidence-calibrations/{first_version}/test")
    assert tested.status_code == 200
    assert tested.json()["status"] == "VALIDATED"

    activated = client.post(f"/api/v1/admin/ai-evolution/confidence-calibrations/{first_version}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert activated.json()["activated_at"] is not None

    status_response = client.get("/api/v1/admin/ai-evolution/calibration-status")
    assert status_response.json()["active_confidence_calibration_version"] == first_version

    _seed_confidence_overconfident_dataset(session, stock, n=100, seed=2)
    second = client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=_PROPOSE_REQUEST).json()
    second_version = second["version"]
    client.post(f"/api/v1/admin/ai-evolution/confidence-calibrations/{second_version}/test")
    activated_second = client.post(f"/api/v1/admin/ai-evolution/confidence-calibrations/{second_version}/activate")
    assert activated_second.json()["status"] == "ACTIVE"

    superseded_first = client.get(f"/api/v1/admin/ai-evolution/confidence-calibrations/{first_version}").json()
    assert superseded_first["status"] == "SUPERSEDED"

    rolled_back = client.post(f"/api/v1/admin/ai-evolution/confidence-calibrations/{first_version}/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["version"] == first_version
    assert rolled_back.json()["status"] == "ACTIVE"

    status_after_rollback = client.get("/api/v1/admin/ai-evolution/calibration-status")
    assert status_after_rollback.json()["active_confidence_calibration_version"] == first_version


def test_activate_requires_validated_status(client, admin, session):
    stock = _confidence_calibration_stock(session)
    _seed_confidence_overconfident_dataset(session, stock, n=60)

    _as(admin)
    created = client.post("/api/v1/admin/ai-evolution/confidence-calibrations", json=_PROPOSE_REQUEST).json()

    response = client.post(f"/api/v1/admin/ai-evolution/confidence-calibrations/{created['version']}/activate")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_confidence_calibration_transition"


def test_activate_404s_for_unknown_version(client, admin):
    _as(admin)
    response = client.post("/api/v1/admin/ai-evolution/confidence-calibrations/does-not-exist/activate")
    assert response.status_code == 404


def test_test_route_404s_for_unknown_version(client, admin):
    _as(admin)
    response = client.post("/api/v1/admin/ai-evolution/confidence-calibrations/does-not-exist/test")
    assert response.status_code == 404
