"""Integration tests for GET /api/v1/admin/market-intelligence/
recurrent-live-scan/status -- BASIRAH -- PRODUCTION-GRADE RECURRENT
LIVE MARKET INTELLIGENCE mandate, Phase 16 (truthful Live Status API).
Mirrors test_radar_v2_route.py's own fixture pattern.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user, get_market_provider
from src.core.db import database
from src.core.db.database import Base, get_db
from src.domain.models import RecurrentScanCycle, RecurrentScanCycleStatus, StaffRole, User
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


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

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_market_provider] = lambda: DevMarketDataProvider()
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


@pytest.fixture
def as_staff():
    staff_user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    main.app.dependency_overrides[get_current_user] = lambda: staff_user
    yield staff_user


@pytest.fixture(autouse=True)
def _no_real_shared_redis(monkeypatch):
    import src.market_data.sahmk.rate_limiter as rate_limiter_module

    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)


def test_status_never_claims_enabled_when_the_flag_is_off(client, session_factory, as_staff, monkeypatch):
    monkeypatch.delenv("LIVE_RECURRENT_SCAN_ENABLED", raising=False)
    response = client.get("/api/v1/admin/market-intelligence/recurrent-live-scan/status")
    assert response.status_code == 200
    body = response.json()
    assert body["live_recurrent_scan_enabled"] is False
    assert body["consumer_feed_affected"] is False
    assert body["last_cycle_id"] is None
    assert body["cycles_today_count"] == 0


def test_status_reports_the_most_recent_real_cycle(client, session_factory, as_staff):
    session = session_factory()
    session.add(
        RecurrentScanCycle(
            cycle_id="cyc-old",
            status=RecurrentScanCycleStatus.SKIPPED_QUOTA,
            skip_reason="upstream_confirmed_exhausted",
            triggered_at=datetime.now(timezone.utc) - timedelta(hours=1),
            finished_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    session.add(
        RecurrentScanCycle(
            cycle_id="cyc-new",
            status=RecurrentScanCycleStatus.SUCCESS,
            signals_new_opportunity_count=2,
            triggered_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/recurrent-live-scan/status")
    assert response.status_code == 200
    body = response.json()
    assert body["last_cycle_id"] == "cyc-new"
    assert body["last_cycle_status"] == "SUCCESS"
    assert body["last_cycle_signals_new_opportunity_count"] == 2
    assert body["cycles_today_count"] == 2


def test_status_never_leaks_the_api_key(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/recurrent-live-scan/status")
    body_text = response.text
    assert "sahmk_api_key" not in body_text.lower()
    assert "api_key" not in body_text.lower()
