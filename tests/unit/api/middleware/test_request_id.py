"""Unit tests for src.api.middleware.request_id, using a minimal
throwaway FastAPI app (not main.app) so this middleware is verified in
isolation."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware, get_request_id


def _app():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/echo")
    def echo(request: Request):
        return {"request_id_from_state": get_request_id(request)}

    return app


def test_response_carries_a_request_id_header_when_none_supplied():
    response = TestClient(_app()).get("/echo")
    assert REQUEST_ID_HEADER in response.headers
    assert len(response.headers[REQUEST_ID_HEADER]) > 0


def test_response_reuses_an_inbound_request_id():
    response = TestClient(_app()).get("/echo", headers={REQUEST_ID_HEADER: "caller-supplied-id"})
    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"


def test_route_handler_sees_the_same_request_id_via_request_state():
    response = TestClient(_app()).get("/echo", headers={REQUEST_ID_HEADER: "caller-supplied-id"})
    assert response.json()["request_id_from_state"] == "caller-supplied-id"


def test_two_requests_without_an_inbound_id_get_different_ids():
    client = TestClient(_app())
    first = client.get("/echo").headers[REQUEST_ID_HEADER]
    second = client.get("/echo").headers[REQUEST_ID_HEADER]
    assert first != second


def test_non_http_scope_passes_through_untouched():
    # ASGI lifespan events (app startup/shutdown -- real, production-
    # reachable traffic through this middleware, exercised on every real
    # app boot) have scope["type"] == "lifespan", not "http" -- using
    # TestClient as a context manager triggers real startup/shutdown
    # lifespan messages, the most direct way to exercise this branch
    # rather than hand-constructing a fake ASGI scope.
    with TestClient(_app()):
        pass  # entering/exiting the context manager alone triggers lifespan events
