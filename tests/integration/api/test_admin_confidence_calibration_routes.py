"""Integration tests for /api/v1/admin/ai-evolution/confidence-calibration/*
-- Phase 3 area 2 (confidence calibration safe production activation).

Before this, ConfidenceCalibrationEngine.propose()/.test()/.activate()/
.rollback() had zero non-test callers anywhere in src/api/ (confirmed
by the Phase 2 audit) -- the engine's full propose -> test -> activate
-> rollback lifecycle, including its DEFAULT_MIN_SAMPLE_SIZE floor, was
real but genuinely unreachable in the shipped product. These tests
drive that lifecycle through the real HTTP routes this milestone adds,
proving: (1) every route is ADMIN-gated, (2) the minimum-sample floor
cannot be bypassed through the API, (3) the full lifecycle transitions
correctly end to end, and (4) activation is real -- it changes what
get_effective_confidence() returns.

Follows test_admin_ai_evolution_routes.py's exact fixture pattern (that
file's own router module) and tests/unit/ai_evolution/
test_confidence_calibration[_decision_v2].py's exact outcome-seeding
helpers (real sklearn fits, no mocking).
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.ai_evolution.confidence_calibration import (
    TRAINING_SOURCE_DECISION_V2,
    ConfidenceCalibrationEngine,
    get_effective_confidence,
)
from src.api.dependencies import get_current_user
from src.core.db.database import Base, get_db
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    StaffRole,
    Stock,
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
def stock(session) -> Stock:
    row = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
    session.add(row)
    session.commit()
    return row


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


def _seed_outcome(session, stock, day_offset, confidence, success, horizon_days=7):
    evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=evaluated_at,
        market_price_at_evaluation=100.0,
        recommendation=RecommendationLabel.BUY,
        total_score=60.0,
        confidence_score=confidence,
        target_price=110.0,
        stop_loss=90.0,
        engine_version="1.0.0",
        source="live_scan",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        RecommendationOutcome(
            snapshot_id=snapshot.id,
            symbol=stock.symbol,
            evaluation_horizon_days=horizon_days,
            due_at=evaluated_at + timedelta(days=horizon_days),
            status=RecommendationOutcomeStatus.SUCCESSFUL if success else RecommendationOutcomeStatus.FAILED,
            evaluated_at=evaluated_at + timedelta(days=horizon_days),
        )
    )


def _seed_overconfident_dataset(session, stock, n=200, seed=42):
    rng = random.Random(seed)
    for i in range(n):
        success = rng.random() < 0.5
        _seed_outcome(session, stock, day_offset=i, confidence=85.0, success=success)
    session.commit()


def _seed_decision_v2_outcome(session, stock, day_offset, confidence, hit_target):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en="Stock 2222",
        decision="BUY_CANDIDATE",
        decision_label_ar="شراء",
        confidence_score=confidence,
        opportunity_quality_score=60.0,
        risk_score=50.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        market_status="OPEN",
        decision_timestamp=ts,
        analysis_version="2.0.0",
        data_source="SAHMK",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        DecisionV2Outcome(
            decision_v2_snapshot_id=snapshot.id,
            symbol=stock.symbol,
            due_at=ts + timedelta(days=7),
            status=DecisionV2OutcomeStatus.TARGET_1_HIT if hit_target else DecisionV2OutcomeStatus.STOP_LOSS_HIT,
            evaluated_at=ts + timedelta(days=7),
        )
    )


def _seed_decision_v2_overconfident_dataset(session, stock, n=200, seed=42):
    rng = random.Random(seed)
    for i in range(n):
        hit_target = rng.random() < 0.5
        _seed_decision_v2_outcome(session, stock, day_offset=i, confidence=85.0, hit_target=hit_target)
    session.commit()


_PERIOD = {"training_period_start": "2026-01-01", "training_period_end": "2026-12-31"}


def test_non_staff_customer_is_rejected_from_every_confidence_calibration_route(client, customer):
    _as(customer)
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD).status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/confidence-calibration").status_code == 403
    assert client.get("/api/v1/admin/ai-evolution/confidence-calibration/v1").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibration/v1/test").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibration/v1/activate").status_code == 403
    assert client.post("/api/v1/admin/ai-evolution/confidence-calibration/v1/rollback").status_code == 403


def test_propose_below_minimum_sample_size_is_rejected_not_silently_fit(client, admin, session, stock):
    """The one safety property this whole area exists to protect: the
    API can never be used to fit and activate a calibration on too
    little real evidence. Only 5 real outcomes exist -- far below the
    engine's own 30-sample floor -- and no request field can loosen it."""
    _as(admin)
    for i in range(5):
        _seed_outcome(session, stock, day_offset=i, confidence=70.0, success=True)
    session.commit()

    response = client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD)
    assert response.status_code == 409
    assert "Insufficient outcome history" in response.json()["error"]["message"]


def test_propose_rejects_an_invalid_source(client, admin):
    _as(admin)
    response = client.post(
        "/api/v1/admin/ai-evolution/confidence-calibration/propose",
        json={**_PERIOD, "source": "not_a_real_source"},
    )
    assert response.status_code == 422


def test_propose_rejects_end_before_start(client, admin):
    _as(admin)
    response = client.post(
        "/api/v1/admin/ai-evolution/confidence-calibration/propose",
        json={"training_period_start": "2026-06-01", "training_period_end": "2026-01-01"},
    )
    assert response.status_code == 422


def test_propose_with_a_real_sufficient_sample_returns_a_draft(client, admin, session, stock):
    _as(admin)
    _seed_overconfident_dataset(session, stock)

    response = client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["training_sample_size"] == 200
    assert body["training_source"] == "legacy_v1"
    assert body["method"] in ("PLATT", "ISOTONIC")


def test_get_and_list_unknown_version_404s(client, admin):
    _as(admin)
    assert client.get("/api/v1/admin/ai-evolution/confidence-calibration/does-not-exist").status_code == 404


def test_list_confidence_calibrations_filters_by_source(client, admin, session, stock):
    _as(admin)
    _seed_overconfident_dataset(session, stock)
    client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD)

    all_models = client.get("/api/v1/admin/ai-evolution/confidence-calibration").json()["models"]
    assert len(all_models) == 1

    legacy_only = client.get(
        "/api/v1/admin/ai-evolution/confidence-calibration", params={"source": "legacy_v1"}
    ).json()["models"]
    assert len(legacy_only) == 1

    decision_v2_only = client.get(
        "/api/v1/admin/ai-evolution/confidence-calibration", params={"source": "decision_v2"}
    ).json()["models"]
    assert decision_v2_only == []


def test_activate_before_test_is_rejected(client, admin, session, stock):
    _as(admin)
    _seed_overconfident_dataset(session, stock)
    version = client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD).json()["version"]

    response = client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{version}/activate")
    assert response.status_code == 409
    assert "VALIDATED" in response.json()["error"]["message"]


def test_full_propose_test_activate_lifecycle_via_routes(client, admin, session, stock):
    """The end-to-end path this whole area was built to enable: propose
    a real fit, test it, activate it -- and confirm activation actually
    changes what get_effective_confidence() returns to the live
    pipeline, not just a status column."""
    _as(admin)
    _seed_overconfident_dataset(session, stock)
    version = client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD).json()["version"]

    tested = client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{version}/test")
    assert tested.status_code == 200
    assert tested.json()["status"] == "VALIDATED"

    activated = client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{version}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert activated.json()["activated_at"] is not None

    calibrated, active_version = get_effective_confidence(session, 85.0)
    assert active_version == version
    # The seeded dataset is systematically overconfident (stated 85,
    # true rate ~50%) -- a real fit must pull the calibrated value
    # meaningfully below the raw 0.85, not leave it unchanged.
    assert calibrated is not None
    assert calibrated < 0.75


def test_rollback_reactivates_a_specific_prior_version(client, admin, session, stock):
    _as(admin)
    _seed_overconfident_dataset(session, stock, seed=1)
    v1 = client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD).json()["version"]
    client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{v1}/test")
    client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{v1}/activate")

    _seed_overconfident_dataset(session, stock, seed=2)
    v2 = client.post("/api/v1/admin/ai-evolution/confidence-calibration/propose", json=_PERIOD).json()["version"]
    client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{v2}/test")
    client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{v2}/activate")

    active_before, active_version_before = get_effective_confidence(session, 85.0)
    assert active_version_before == v2

    rolled_back = client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{v1}/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "ACTIVE"

    _, active_version_after = get_effective_confidence(session, 85.0)
    assert active_version_after == v1


def test_decision_v2_source_propose_and_activate_end_to_end(client, admin, session, stock):
    """The route must thread `source` through correctly to the
    decision_v2 ledger (DecisionV2Snapshot/DecisionV2Outcome) -- a
    distinct training pool from legacy_v1, per training_source scoping
    in ConfidenceCalibrationEngine.get_active_model()."""
    _as(admin)
    _seed_decision_v2_overconfident_dataset(session, stock)

    proposed = client.post(
        "/api/v1/admin/ai-evolution/confidence-calibration/propose",
        json={**_PERIOD, "source": "decision_v2"},
    )
    assert proposed.status_code == 200
    body = proposed.json()
    assert body["training_source"] == "decision_v2"
    version = body["version"]

    client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{version}/test")
    activated = client.post(f"/api/v1/admin/ai-evolution/confidence-calibration/{version}/activate")
    assert activated.status_code == 200

    calibrated, active_version = get_effective_confidence(session, 85.0, source=TRAINING_SOURCE_DECISION_V2)
    assert active_version == version
    assert calibrated is not None

    # legacy_v1 must remain untouched by a decision_v2 activation.
    legacy_active = ConfidenceCalibrationEngine().get_active_model(session)
    assert legacy_active is None
