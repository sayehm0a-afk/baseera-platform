"""Integration tests for GET /api/v1/stocks, GET /api/v1/stocks/{symbol}
-- unauthenticated by design, see routes/stocks.py's module docstring."""

from tests.integration.api._helpers import clear_overrides, make_client, make_session, seed_stock


def teardown_function():
    clear_overrides()


def test_list_stocks_returns_seeded_stocks():
    session = make_session()
    seed_stock(session, symbol="1111", name_en="Alpha Co")
    seed_stock(session, symbol="2222", name_en="Beta Co")
    client = make_client(session)

    response = client.get("/api/v1/stocks")

    assert response.status_code == 200
    body = response.json()
    symbols = {s["symbol"] for s in body["data"]}
    assert symbols == {"1111", "2222"}
    assert body["pagination"]["total"] == 2


def test_list_stocks_is_paginated():
    session = make_session()
    for i in range(5):
        seed_stock(session, symbol=f"100{i}", name_en=f"Co {i}")
    client = make_client(session)

    response = client.get("/api/v1/stocks?page=1&page_size=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {"page": 1, "page_size": 2, "total": 5, "has_next": True}


def test_list_stocks_last_page_has_next_false():
    session = make_session()
    for i in range(3):
        seed_stock(session, symbol=f"100{i}", name_en=f"Co {i}")
    client = make_client(session)

    response = client.get("/api/v1/stocks?page=2&page_size=2")

    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["has_next"] is False


def test_get_stock_returns_detail():
    session = make_session()
    seed_stock(session, symbol="1111", name_en="Alpha Co")
    client = make_client(session)

    response = client.get("/api/v1/stocks/1111")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["symbol"] == "1111"
    assert body["data"]["name_en"] == "Alpha Co"
    assert body["data"]["currency"] == "SAR"


def test_get_stock_404_for_unknown_symbol():
    session = make_session()
    client = make_client(session)

    response = client.get("/api/v1/stocks/9999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
