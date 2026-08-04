"""Phase 2 Foundation Cleanup, goal 2: the legacy runtime-kernel
endpoints (/api/tasks, /api/tasks/{task_id}, /api/agents/{agent_id})
were previously reachable by any anonymous caller (audit finding --
"three genuinely concerning" unauthenticated endpoints with zero real
product dependents). They now require require_staff_role(StaffRole.ADMIN),
same as every other admin/ops route in this codebase.

test_admin_rbac_coverage.py already proves this statically (every
admin/legacy route's dependency tree includes require_staff_role); this
file proves the same thing as a live HTTP round-trip, matching the
functional-test style test_admin_market_intelligence_route.py already
uses for the admin router.
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
def as_non_staff():
    user = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: user
    yield user


@pytest.fixture
def as_staff():
    user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    main.app.dependency_overrides[get_current_user] = lambda: user
    yield user


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/tasks", {"task_id": "t1", "agent_id": "a1", "task_type": "test", "data": {}}),
        ("get", "/api/tasks/t1", None),
        ("get", "/api/agents/a1", None),
    ],
)
def test_unauthenticated_caller_is_rejected(client, method, path, json_body):
    response = getattr(client, method)(path, json=json_body) if json_body is not None else getattr(client, method)(path)
    assert response.status_code in (401, 403)


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/tasks", {"task_id": "t1", "agent_id": "a1", "task_type": "test", "data": {}}),
        ("get", "/api/tasks/t1", None),
        ("get", "/api/agents/a1", None),
    ],
)
def test_non_staff_caller_is_rejected(client, as_non_staff, method, path, json_body):
    response = getattr(client, method)(path, json=json_body) if json_body is not None else getattr(client, method)(path)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/tasks", {"task_id": "t1", "agent_id": "a1", "task_type": "test", "data": {}}),
        ("get", "/api/tasks/t1", None),
        ("get", "/api/agents/a1", None),
    ],
)
def test_staff_caller_reaches_the_route_handler(client, as_staff, method, path, json_body):
    """The kernel is never initialized in the test process (no
    lifespan startup event runs under TestClient without a context
    manager), so a staff caller reaching the handler gets 503 "not
    available" -- proof the auth gate let them through, not proof the
    legacy kernel itself works, which is out of scope for this
    security-hardening change."""
    response = getattr(client, method)(path, json=json_body) if json_body is not None else getattr(client, method)(path)
    assert response.status_code != 401
    assert response.status_code != 403
