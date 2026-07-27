"""Integration tests for the /metrics and /health/ready endpoints wired
into main.py. Both call src.core.db.database.get_session_factory() and
src.auth.token_store.get_redis_client() *directly* (not through FastAPI's
Depends(get_db), which the conftest.py `client` fixture overrides), so
they always hit the real DATABASE_URL/REDIS_HOST -- these tests are
skipped when a real Postgres/Redis aren't reachable, mirroring
test_auth_routes.py's Redis-availability gate.
"""

import pytest
from fastapi.testclient import TestClient

import main


def _redis_available() -> bool:
    try:
        import redis

        return redis.Redis(host="localhost", port=6379, socket_connect_timeout=1).ping()
    except Exception:
        return False


def _postgres_available() -> bool:
    try:
        from src.core.db.database import get_session_factory
        from sqlalchemy import text

        session = get_session_factory()()
        try:
            session.execute(text("SELECT 1"))
            return True
        finally:
            session.close()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_redis_available() and _postgres_available()), reason="Real Postgres/Redis not available"
)


@pytest.fixture
def client():
    return TestClient(main.app)


def test_metrics_is_served_as_real_prometheus_exposition_format_not_json(client):
    # Regression test: a plain `str` return value from a FastAPI route
    # is auto-JSON-encoded (quoted, with escaped newlines) unless
    # explicitly wrapped in a Response -- Prometheus can't scrape that.
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.startswith("# HELP")
    assert '\\n' not in response.text.splitlines()[0]


def test_metrics_reflects_the_new_phase_10_metric_names(client):
    response = client.get("/metrics")
    body = response.text
    for metric_name in (
        "basirah_logins_total",
        "basirah_registrations_total",
        "basirah_active_sessions",
        "basirah_trial_expirations_total",
        "basirah_ai_requests_total",
        "basirah_ai_tokens_total",
        "basirah_admin_actions_total",
    ):
        assert metric_name in body


def test_health_ready_reports_real_database_and_redis_probes(client):
    # TestClient(main.app) is deliberately never entered as a context
    # manager (see conftest.py) so the app's startup lifecycle -- and
    # therefore `kernel` -- never runs; this asserts on the DB/Redis
    # probes specifically, not the overall status, which stays 503
    # for the unrelated "kernel not initialized" reason.
    response = client.get("/health/ready")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "'database': True" in detail
    assert "'redis': True" in detail
