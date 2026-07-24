"""Integration tests for GET /api/v1/market-data/{symbol}/ohlcv."""

import os

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


def test_ohlcv_returns_all_seeded_bars_within_default_page_size():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock, bar_count=40)
    client = make_client(session)

    response = client.get("/api/v1/market-data/1111/ohlcv", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 40
    assert body["pagination"]["total"] == 40
    # Ascending order (oldest first), matching load_price_bars' own ordering.
    assert body["data"][0]["close"] < body["data"][-1]["close"]


def test_ohlcv_requires_authentication():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/market-data/1111/ohlcv")

    assert response.status_code == 401


def test_ohlcv_404_for_unknown_symbol():
    session = make_session()
    client = make_client(session)

    response = client.get("/api/v1/market-data/9999/ohlcv", headers=_AUTH_HEADERS)

    assert response.status_code == 404


def test_ohlcv_is_paginated():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock, bar_count=40)
    client = make_client(session)

    response = client.get("/api/v1/market-data/1111/ohlcv?page=1&page_size=10", headers=_AUTH_HEADERS)

    body = response.json()
    assert len(body["data"]) == 10
    assert body["pagination"] == {"page": 1, "page_size": 10, "total": 40, "has_next": True}


def test_ohlcv_empty_result_for_stock_with_no_price_history():
    session = make_session()
    seed_stock(session)
    client = make_client(session)

    response = client.get("/api/v1/market-data/1111/ohlcv", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0
    assert body["meta"]["freshness"] == "unknown"


def test_ohlcv_respects_start_end_query_params():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock, bar_count=40)
    client = make_client(session)

    # Bar 0 is 2024-01-01; request a narrow window that should only match a few bars.
    response = client.get(
        "/api/v1/market-data/1111/ohlcv",
        params={"start": "2024-01-01T00:00:00Z", "end": "2024-01-03T00:00:00Z"},
        headers=_AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 3  # Jan 1, 2, 3


def test_provider_health_returns_dev_provider_status_by_default():
    os.environ.pop("MARKET_DATA_PROVIDER", None)
    session = make_session()
    client = make_client(session)

    response = client.get("/api/v1/market-data/provider/health", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["provider"] == "dev"
    assert body["data"]["status"] == "healthy"
    assert "request_id" in body["meta"]


def test_provider_health_requires_authentication():
    session = make_session()
    client = make_client(session)

    response = client.get("/api/v1/market-data/provider/health")

    assert response.status_code == 401
