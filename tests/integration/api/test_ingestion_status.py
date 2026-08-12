"""Integration test for GET /ingestion/status. Doesn't use FastAPI's
Depends()-based DB session (it builds its own via
database.get_session_factory()), so it's tested by monkeypatching that
function directly rather than app.dependency_overrides.

Staff-gated as of the M8 security acceptance pass -- this route
predates Phase 10's RBAC layer and was previously reachable by any
unauthenticated caller (docs/ADMIN_AND_RBAC.md §5,
docs/THREAT_MODEL.md T18). get_current_user is overridden to a staff
user for the success-path tests, matching the pattern already used in
test_admin_routes.py; a dedicated test below asserts an anonymous
caller is now rejected.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user
from src.core.db import database
from src.core.db.database import Base
from src.domain.models import IngestionJobStatus, IngestionRunLog, StaffRole, User


@pytest.fixture
def session_factory(monkeypatch):
    # StaticPool + check_same_thread=False: TestClient dispatches requests
    # on a background thread (via the anyio portal), but a plain
    # "sqlite:///:memory:" engine defaults to SingletonThreadPool, which
    # hands each thread its own *separate, empty* in-memory database. Without
    # this, the route's queries run against a DB that never got
    # Base.metadata.create_all() applied to it, even though this fixture's
    # own connection does have the tables.
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin_client(session_factory):
    admin = User(id=1, email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    main.app.dependency_overrides[get_current_user] = lambda: admin
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


def test_ingestion_status_rejects_an_unauthenticated_caller(client, session_factory):
    response = client.get("/ingestion/status")
    assert response.status_code == 401


def test_ingestion_status_rejects_a_non_staff_customer(client, session_factory):
    customer = User(id=2, email="customer@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: customer
    try:
        response = client.get("/ingestion/status")
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 403


def test_ingestion_status_when_scheduler_never_started(admin_client, session_factory):
    response = admin_client.get("/ingestion/status")
    assert response.status_code == 200
    body = response.json()
    assert body["scheduler_running"] is False
    assert body["jobs"] == {}


def test_ingestion_status_reports_the_most_recent_run_per_job(admin_client, session_factory):
    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="historical_ohlcv",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
            duration_seconds=5.0,
            symbols_requested=2,
            symbols_succeeded=2,
            rows_upserted=12,
            status=IngestionJobStatus.SUCCESS,
        )
    )
    session.add(
        IngestionRunLog(
            job_name="historical_ohlcv",
            started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 2, 0, 0, 3, tzinfo=timezone.utc),
            duration_seconds=3.0,
            symbols_requested=2,
            symbols_succeeded=2,
            rows_upserted=2,
            status=IngestionJobStatus.SUCCESS,
        )
    )
    session.commit()
    session.close()

    response = admin_client.get("/ingestion/status")
    assert response.status_code == 200
    body = response.json()
    assert "historical_ohlcv" in body["jobs"]
    # the *most recent* (Jan 2) run, not the first one
    assert body["jobs"]["historical_ohlcv"]["started_at"].startswith("2026-01-02")
    assert body["jobs"]["historical_ohlcv"]["rows_upserted"] == 2
    assert body["jobs"]["historical_ohlcv"]["status"] == "success"


def test_ingestion_status_never_exposes_credentials(admin_client, session_factory):
    response = admin_client.get("/ingestion/status")
    body_text = response.text.lower()
    assert "sahmk_api_key" not in body_text
    assert "shmk_" not in body_text
