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
    DiscoveredPattern,
    ReflectionReport,
    StaffRole,
    User,
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
