"""Integration tests for RequestIDMiddleware, wired into main.py. Uses
the real `main.app` directly (no DB fixture needed) -- request-ID
assignment happens in the ASGI middleware layer regardless of what the
route below it does.
"""

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_a_request_with_no_incoming_request_id_gets_one_assigned(client):
    response = client.get("/health/live")
    assert response.headers["X-Request-ID"]


def test_an_incoming_request_id_is_echoed_back_unchanged(client):
    response = client.get("/health/live", headers={"X-Request-ID": "caller-supplied-id-123"})
    assert response.headers["X-Request-ID"] == "caller-supplied-id-123"


def test_two_requests_with_no_incoming_id_get_different_ids(client):
    first = client.get("/health/live").headers["X-Request-ID"]
    second = client.get("/health/live").headers["X-Request-ID"]
    assert first != second
