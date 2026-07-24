"""Integration tests for the global exception handlers
(src/api/error_handlers.py) -- specifically the final Exception
catch-all, which no route's own expected-failure path exercises."""

import os
from unittest.mock import patch

from tests.integration.api._helpers import (
    clear_overrides,
    make_client,
    make_session,
    seed_price_history,
    seed_stock,
)

_AUTH_HEADERS = {"X-API-Key": "test-api-key"}


def setup_function():
    os.environ["API_KEY"] = "test-api-key"


def teardown_function():
    clear_overrides()


def test_unexpected_exception_returns_500_with_error_envelope_and_does_not_leak_internal_text():
    # Starlette's ServerErrorMiddleware -- which runs the Exception
    # handler registered in error_handlers.py -- sends that handler's
    # response to the client *and then re-raises the original exception*
    # afterward, deliberately, so an ASGI server (uvicorn) can still log
    # the crash even though the client already got a clean response.
    # TestClient's default raise_server_exceptions=True re-raises that
    # exception into the test process too; raise_server_exceptions=False
    # is the documented way to instead inspect the response the client
    # actually received, which is what this test verifies.
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session, raise_server_exceptions=False)

    with patch(
        "src.api.routes.analysis.TechnicalAnalysisEngine.analyze",
        side_effect=RuntimeError("internal db connection string: postgres://secret"),
    ):
        response = client.get("/api/v1/analysis/1111/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "An unexpected error occurred"
    assert "postgres://secret" not in response.text
    assert "request_id" in body["error"]


def test_value_error_from_engine_maps_to_422():
    # TechnicalAnalysisEngine.analyze()'s own documented ValueError (too
    # little history) -- verified end to end via a genuinely short
    # history rather than a mock, since this is real, existing behavior.
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock, bar_count=10)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_pre_existing_routes_are_unaffected_by_the_new_global_handlers():
    # Backward-compatibility spot check alongside the dedicated
    # tests/unit/test_main_error_handling.py suite: an old route's
    # bare HTTPException must still return FastAPI's default
    # {"detail": ...} shape, not this milestone's {"error": {...}} envelope.
    session = make_session()
    client = make_client(session)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert "detail" in response.json()
    assert "error" not in response.json()
