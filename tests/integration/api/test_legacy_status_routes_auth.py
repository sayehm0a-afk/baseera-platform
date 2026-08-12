"""M8 security acceptance pass: GET /stats and GET /market-data/status
predate Phase 10's RBAC layer and were previously reachable by any
unauthenticated caller, leaking internal operational detail (runtime
kernel stats, active market-data provider/health) -- see
docs/ADMIN_AND_RBAC.md §5 and docs/THREAT_MODEL.md T18. Both routes now
require staff access; these tests are the regression coverage for that
fix (GET /ingestion/status's equivalent coverage lives in
test_ingestion_status.py).
"""

import pytest
from fastapi.testclient import TestClient

import main
from src.api.dependencies import get_current_user
from src.domain.models import StaffRole, User


@pytest.fixture
def client():
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def admin_user():
    return User(id=1, email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)


@pytest.fixture
def customer_user():
    return User(id=2, email="customer@example.com", password_hash="hashed", is_staff=False)


@pytest.mark.parametrize("path", ["/stats", "/market-data/status"])
def test_rejects_an_unauthenticated_caller(client, path):
    response = client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/stats", "/market-data/status"])
def test_rejects_a_non_staff_customer(client, customer_user, path):
    main.app.dependency_overrides[get_current_user] = lambda: customer_user
    response = client.get(path)
    assert response.status_code == 403


def test_stats_reachable_by_staff_once_authenticated(client, admin_user):
    main.app.dependency_overrides[get_current_user] = lambda: admin_user
    response = client.get("/stats")
    # The legacy runtime kernel is only initialized during the app's
    # lifespan startup, which TestClient(main.app) (no `with` context
    # manager) never runs -- so a staff caller correctly clears the auth
    # gate and reaches the route's own "kernel not initialized" branch.
    # That branch's HTTPException(503) is itself caught by the route's
    # blanket `except Exception` and re-wrapped as 500 -- a pre-existing
    # quirk of this legacy route, unrelated to the auth fix under test
    # here. What matters for this regression test is that the request
    # got *past* authentication (401/403) at all.
    assert response.status_code == 500


def test_market_data_status_reachable_by_staff_once_authenticated(client, admin_user):
    main.app.dependency_overrides[get_current_user] = lambda: admin_user
    response = client.get("/market-data/status")
    assert response.status_code == 200
    body = response.json()
    assert "market_data" in body and "fundamentals" in body
