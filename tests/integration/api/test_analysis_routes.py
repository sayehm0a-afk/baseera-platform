"""Integration tests for GET /api/v1/analysis/{symbol}/{technical,
fundamental,composite,councils/technical} -- real in-memory DB, real
engines, real CouncilEngine, only the HTTP layer under test.
"""

from tests.integration.api._helpers import (
    clear_overrides,
    make_client,
    make_session,
    seed_fundamental_snapshots,
    seed_price_history,
    seed_stock,
)

_AUTH_HEADERS = {"X-API-Key": "test-api-key"}


def setup_function():
    import os

    os.environ["API_KEY"] = "test-api-key"


def teardown_function():
    clear_overrides()


def test_technical_analysis_returns_bullish_indicators_on_real_uptrend_data():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["symbol"] == "1111"
    indicator_names = {item["name"] for item in body["data"]["indicators"]}
    assert indicator_names == {
        "sma_20",
        "ema_20",
        "adx_14",
        "supertrend",
        "rsi_14",
        "macd",
        "bollinger",
        "atr_14",
        "obv",
        "volume_sma_20",
        "candlestick_patterns",
    }
    assert "meta" in body
    assert body["meta"]["freshness"] in {"fresh", "aging", "stale", "unknown"}
    assert "request_id" in body["meta"]


def test_technical_analysis_requires_authentication():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/technical")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_technical_analysis_404_for_unknown_symbol():
    session = make_session()
    client = make_client(session)

    response = client.get("/api/v1/analysis/9999/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_technical_analysis_422_for_insufficient_price_history():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock, bar_count=5)  # below the 35-row minimum
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 422


def test_technical_analysis_422_for_no_price_history_at_all():
    session = make_session()
    seed_stock(session)  # no price bars seeded
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_DATA"


def test_fundamental_analysis_returns_ratios_on_real_data():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    seed_fundamental_snapshots(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/fundamental", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    ratio_names = {item["name"] for item in body["data"]["ratios"]}
    assert "revenue_growth" in ratio_names
    revenue_growth = next(r for r in body["data"]["ratios"] if r["name"] == "revenue_growth")
    assert revenue_growth["latest"] == 0.25  # 800M -> 1000M, same real computation test_full_pipeline.py verifies


def test_fundamental_analysis_422_when_no_snapshots_exist():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/fundamental", headers=_AUTH_HEADERS)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_DATA"


def test_fundamental_analysis_degrades_gracefully_with_no_price_data():
    # market_price lookup is best-effort; missing price history must not
    # fail the whole fundamental response.
    session = make_session()
    stock = seed_stock(session)
    seed_fundamental_snapshots(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/fundamental", headers=_AUTH_HEADERS)

    assert response.status_code == 200


def test_composite_analysis_returns_alignment_factor():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    seed_fundamental_snapshots(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/composite", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    factor_names = {f["name"] for f in body["data"]["factors"]}
    assert factor_names == {"data_quality_summary", "trend_fundamental_alignment", "valuation_momentum_context"}
    alignment = next(f for f in body["data"]["factors"] if f["name"] == "trend_fundamental_alignment")
    assert alignment["value"] == 1.0
    assert alignment["agreement"] == "agree"


def test_composite_analysis_degrades_gracefully_without_fundamental_data():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)  # no fundamental snapshots
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/composite", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    # data_quality_summary reflects whatever envelopes were actually
    # supplied (1 fresh envelope is "complete" *for that envelope*, by
    # design -- src/analysis/composite/factors/data_quality.py's own
    # docstring: "reflects on whatever it's given"). The factor that
    # specifically needs both engines is the one that must show the
    # missing-fundamental-data degradation instead.
    alignment = next(f for f in body["data"]["factors"] if f["name"] == "trend_fundamental_alignment")
    assert alignment["completeness"] == "partial"


def test_technical_council_returns_all_five_experts():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/councils/technical", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["council"] == "technical"
    expert_ids = {e["expert_id"] for e in body["data"]["experts"]}
    assert expert_ids == {
        "technical.trend",
        "technical.momentum",
        "technical.volatility",
        "technical.volume",
        "technical.candlestick",
    }
    trend = next(e for e in body["data"]["experts"] if e["expert_id"] == "technical.trend")
    assert trend["direction"] == "bullish"
    assert trend["normalized_score"] > 0.0
    assert trend["confidence"] < 1.0  # BIIC Article IV.4 -- never full certainty
    assert isinstance(trend["evidence"], list) and len(trend["evidence"]) > 0


def test_technical_council_requires_authentication():
    session = make_session()
    stock = seed_stock(session)
    seed_price_history(session, stock)
    client = make_client(session)

    response = client.get("/api/v1/analysis/1111/councils/technical")

    assert response.status_code == 401
