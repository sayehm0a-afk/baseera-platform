"""Integration tests for GET /health/market-data -- the safe
operational status endpoint. Deliberately does not require real
Postgres/Redis (unlike test_monitoring_endpoints.py's /health/ready
tests): this route never touches either.
"""

import pytest
from fastapi.testclient import TestClient

import main
from src.market_data import provider_factory


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    monkeypatch.delenv("STRICT_REAL_DATA", raising=False)
    monkeypatch.delenv("ALLOW_SYNTHETIC_DATA", raising=False)
    yield
    provider_factory.reset_provider_cache()


def test_market_data_health_reports_configuration_without_a_running_provider(client):
    response = client.get("/health/market-data")
    assert response.status_code == 200
    body = response.json()
    for field in (
        "configured_provider", "strict_real_data", "synthetic_allowed",
        "sahmk_key_present", "current_provider_kind", "last_connectivity_status",
        "last_connectivity_at", "last_real_data_at", "last_scan_source",
        "can_publish_recommendations",
    ):
        assert field in body


def test_market_data_health_reflects_strict_mode_flags(client, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    response = client.get("/health/market-data")
    body = response.json()
    assert body["strict_real_data"] is True
    assert body["synthetic_allowed"] is False
    # Nothing has been selected yet in this process -- strict mode
    # must never report "permitted to publish" without real proof.
    assert body["can_publish_recommendations"] is False


def test_market_data_health_never_leaks_the_api_key(client, monkeypatch):
    secret = "shmk_live_do_not_leak_9f8e7d6c"
    monkeypatch.setenv("SAHMK_API_KEY", secret)
    response = client.get("/health/market-data")
    assert secret not in response.text
    assert response.json()["sahmk_key_present"] is True
