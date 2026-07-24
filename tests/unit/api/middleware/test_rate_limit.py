"""Unit tests for src.api.middleware.rate_limit, using a minimal
throwaway FastAPI app -- see test_request_id.py for the same technique."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middleware.rate_limit import RateLimitMiddleware, _RateLimiter


def _app(max_requests: int, window_seconds: int):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=max_requests, window_seconds=window_seconds)

    @app.get("/ping")
    def ping():
        return {"pong": True}

    return app


def test_requests_within_the_limit_all_succeed():
    client = TestClient(_app(max_requests=3, window_seconds=60))
    for _ in range(3):
        response = client.get("/ping")
        assert response.status_code == 200


def test_request_beyond_the_limit_is_rejected_with_429():
    client = TestClient(_app(max_requests=2, window_seconds=60))
    client.get("/ping")
    client.get("/ping")
    response = client.get("/ping")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_429_response_includes_retry_after_header():
    client = TestClient(_app(max_requests=1, window_seconds=30))
    client.get("/ping")
    response = client.get("/ping")
    assert response.headers["Retry-After"] == "30"


def test_different_clients_have_independent_limits():
    # TestClient always presents the same client host, so this exercises
    # _RateLimiter directly for the per-key isolation guarantee instead.
    limiter = _RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("client-a", now=1000.0) is True
    assert limiter.is_allowed("client-b", now=1000.0) is True
    assert limiter.is_allowed("client-a", now=1000.0) is False


def test_a_new_window_resets_the_count():
    limiter = _RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("client-a", now=0.0) is True
    assert limiter.is_allowed("client-a", now=30.0) is False  # still same 60s window
    assert limiter.is_allowed("client-a", now=61.0) is True  # new window


def test_pruning_removes_stale_windows_not_the_current_one():
    limiter = _RateLimiter(max_requests=5, window_seconds=10)
    limiter.is_allowed("client-a", now=0.0)  # window 0
    limiter.is_allowed("client-a", now=15.0)  # window 1 -- prunes window 0
    assert (("client-a", 0)) not in limiter._counts
    assert (("client-a", 1)) in limiter._counts


def test_non_http_scope_passes_through_untouched():
    # See test_request_id.py's identical test for why this uses
    # TestClient as a context manager -- real ASGI lifespan events are
    # the natural, production-reachable way scope["type"] != "http"
    # traffic reaches this middleware.
    with TestClient(_app(max_requests=1, window_seconds=60)):
        pass
