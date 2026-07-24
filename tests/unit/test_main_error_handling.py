"""Unit tests for main.py's route-level exception handling.

Verifies two things per route: (1) an unhandled internal exception
never leaks its raw text to the HTTP client, only a generic message
(the real exception is still logged server-side via
logger.error(..., exc_info=True)); (2) a route's own intentionally-
raised HTTPException (e.g. 503 "kernel not initialized") is not
miscategorized as a 500 by the broad `except Exception` clause below
it -- confirmed by the presence of an `except HTTPException: raise`
guard before the generic handler.

Uses a plain (non-context-manager) TestClient so FastAPI's lifespan/
startup event never runs -- exercising route logic in isolation
without needing a live Redis/DB, consistent with these routes' own
kernel-is-None guard clauses.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import main


def _client():
    return TestClient(main.app)


def test_readiness_check_returns_503_not_500_when_kernel_uninitialized():
    main.kernel = None
    response = _client().get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "kernel not initialized"


def test_stats_returns_503_not_500_when_kernel_uninitialized():
    main.kernel = None
    response = _client().get("/stats")
    assert response.status_code == 503
    assert response.json()["detail"] == "Kernel not initialized"


def test_stats_does_not_leak_internal_exception_text():
    fake_kernel = MagicMock()
    fake_kernel.get_stats.side_effect = RuntimeError("internal db connection string: postgres://secret")
    main.kernel = fake_kernel

    response = _client().get("/stats")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve statistics"
    assert "postgres://secret" not in response.text


def test_readiness_check_does_not_leak_internal_exception_text():
    fake_kernel = MagicMock()
    fake_kernel.health_check.side_effect = RuntimeError("sensitive internal detail")
    main.kernel = fake_kernel

    response = _client().get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Service not ready"
    assert "sensitive internal detail" not in response.text


def test_submit_task_does_not_leak_internal_exception_text():
    fake_kernel = MagicMock()
    fake_kernel.service_layer = MagicMock()
    fake_kernel.service_layer.submit_task = AsyncMock(
        side_effect=RuntimeError("sensitive internal detail")
    )
    main.kernel = fake_kernel

    response = _client().post(
        "/api/tasks",
        json={"task_id": "t1", "agent_id": "a1", "task_type": "test", "data": {}},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to submit task"
    assert "sensitive internal detail" not in response.text


def test_get_task_status_does_not_leak_internal_exception_text():
    fake_kernel = MagicMock()
    fake_kernel.service_layer = MagicMock()
    fake_kernel.service_layer.get_task_status = AsyncMock(
        side_effect=RuntimeError("sensitive internal detail")
    )
    main.kernel = fake_kernel

    response = _client().get("/api/tasks/abc123")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve task status"
    assert "sensitive internal detail" not in response.text


def test_get_agent_status_does_not_leak_internal_exception_text():
    fake_kernel = MagicMock()
    fake_kernel.service_layer = MagicMock()
    fake_kernel.service_layer.get_agent_status = AsyncMock(
        side_effect=RuntimeError("sensitive internal detail")
    )
    main.kernel = fake_kernel

    response = _client().get("/api/agents/abc123")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve agent status"
    assert "sensitive internal detail" not in response.text


def test_get_task_status_404_is_not_miscategorized_as_500():
    fake_kernel = MagicMock()
    fake_kernel.service_layer = MagicMock()
    fake_kernel.service_layer.get_task_status = AsyncMock(return_value=None)
    main.kernel = fake_kernel

    response = _client().get("/api/tasks/does-not-exist")

    assert response.status_code == 404
