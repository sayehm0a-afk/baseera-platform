"""Integration tests for GET /api/v1/stocks/* -- real FastAPI routing,
real dependency injection, real TechnicalAnalysisEngine/
FundamentalAnalysisEngine, against an in-memory SQLite DB and Dev*
providers (see conftest.py). No live network call anywhere.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import FundamentalSnapshot, PeriodType, PriceBar, Stock, Timeframe
from src.market_data.providers.market_data_provider import IMarketDataProvider, ProviderHealth


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    """Every /api/v1/stocks/* route now requires require_active_
    subscription() (Phase 13 P13.5) -- see conftest.py's
    authenticated_as_staff for why this is opt-in per file rather than
    on db_session/client directly."""


class _AlwaysDownProvider(IMarketDataProvider):
    """A minimal IMarketDataProvider that fails every real call --
    used to test how routes degrade when the market data provider is
    unreachable."""

    async def authenticate(self):
        return False

    async def get_stock_data(self, symbol):
        raise CircuitBreakerOpenError()

    async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
        raise CircuitBreakerOpenError()

    async def get_index_data(self, index_name):
        raise NotImplementedError

    async def get_market_news(self, limit=10):
        raise NotImplementedError

    async def health_check(self):
        return ProviderHealth.UNHEALTHY

    async def disconnect(self):
        pass


def _make_stock(session: Session, symbol: str = "2222") -> Stock:
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _add_bars(session: Session, stock: Stock, count: int) -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=Decimal("30.0") + i * Decimal("0.1"),
                high=Decimal("31.0") + i * Decimal("0.1"),
                low=Decimal("29.0") + i * Decimal("0.1"),
                close=Decimal("30.5") + i * Decimal("0.1"),
                volume=1000 + i,
            )
        )
    session.commit()


def _add_fundamentals(
    session: Session, stock: Stock, fiscal_year: int = 2025, revenue: str = "1000000"
) -> None:
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=date(fiscal_year, 12, 31),
            revenue=Decimal(revenue),
            net_income=Decimal("100000"),
            total_assets=Decimal("5000000"),
            total_liabilities=Decimal("2000000"),
            total_equity=Decimal("3000000"),
            current_assets=Decimal("1500000"),
            current_liabilities=Decimal("800000"),
            shares_outstanding=1_000_000,
            eps=Decimal("0.1"),
            dividend_per_share=Decimal("0.02"),
            source="dev-synthetic",
            is_synthetic=True,
        )
    )
    session.commit()


# --- GET /api/v1/stocks/{symbol} --------------------------------------


def test_get_stock_returns_registered_stock(client, db_session):
    _make_stock(db_session)
    response = client.get("/api/v1/stocks/2222")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["name_en"] == "Saudi Aramco"
    assert body["sector"] == "Energy"


def test_get_stock_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "stock_not_found", "message": "No stock is registered for symbol '9999'."}
    }


# --- GET /api/v1/stocks/{symbol}/quote ---------------------------------


def test_get_quote_returns_synthetic_dev_quote_labeled_as_such(client, db_session):
    response = client.get("/api/v1/stocks/2222/quote")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["source"] == "dev-synthetic"
    assert body["is_synthetic"] is True
    assert body["low"] <= body["open"] <= body["high"]


def test_get_quote_422_for_malformed_symbol(client, db_session):
    response = client.get("/api/v1/stocks/NOTVALID/quote")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_symbol_format"


def test_get_quote_503_when_provider_unavailable(client, db_session, monkeypatch):
    import main
    from src.api.dependencies import get_market_provider

    main.app.dependency_overrides[get_market_provider] = lambda: _AlwaysDownProvider()
    try:
        response = client.get("/api/v1/stocks/2222/quote")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


class _DailyBarUnavailableButLiveQuoteWorksProvider(IMarketDataProvider):
    """Regression for the real production defect (confirmed 2026-08-06):
    SAHMK does not finalize a session's own daily bar until after that
    session closes, so get_stock_data() (which requires *today's*
    specific bar) raised for every symbol, at every hour, until end-
    of-day data landed -- even though SAHMK's real-time quote endpoint
    had live data the entire time. This provider models exactly that
    split: get_stock_data() fails like the real SAHMK provider did,
    get_latest_quote() (opportunistic, matching context_builder.py's
    own getattr(provider, "get_latest_quote", None) pattern) succeeds."""

    async def authenticate(self):
        return True

    async def get_stock_data(self, symbol):
        raise CircuitBreakerOpenError()

    async def get_latest_quote(self, symbol):
        return {
            "symbol": symbol,
            "price": 26.68,
            "change": 0.12,
            "change_percent": 0.45,
            "volume": 500_000,
            "timestamp": datetime(2026, 8, 6, 9, 30, tzinfo=timezone.utc).isoformat(),
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
        raise CircuitBreakerOpenError()

    async def get_index_data(self, index_name):
        raise NotImplementedError

    async def get_market_news(self, limit=10):
        raise NotImplementedError

    async def health_check(self):
        return ProviderHealth.HEALTHY

    async def disconnect(self):
        pass


def test_get_quote_falls_back_to_live_quote_when_daily_bar_not_yet_finalized(client, db_session):
    import main
    from src.api.dependencies import get_market_provider

    main.app.dependency_overrides[get_market_provider] = lambda: _DailyBarUnavailableButLiveQuoteWorksProvider()
    try:
        response = client.get("/api/v1/stocks/2222/quote")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["close"] == 26.68
    assert body["open"] is None
    assert body["high"] is None
    assert body["low"] is None
    assert body["source"] == "sahmk"
    assert body["is_synthetic"] is False


class _FailIfCalledProvider(IMarketDataProvider):
    """Priority-2 quota fix regression: get_stock_data() must never be
    called when an already-ingested, same-day local PriceBar exists --
    that would be a duplicate SAHMK request for data already sitting in
    the database. Raising AssertionError (rather than just tracking a
    call count) makes the assertion fail loudly, inside the request,
    if the route regresses back to always fetching live."""

    async def authenticate(self):
        return True

    async def get_stock_data(self, symbol):
        raise AssertionError("get_stock_data() must not be called when a fresh local bar already exists")

    async def get_latest_quote(self, symbol):
        return {
            "symbol": symbol,
            "price": 30.9,
            "change": 0.1,
            "change_percent": 0.3,
            "volume": 15000,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
        raise NotImplementedError

    async def get_index_data(self, index_name):
        raise NotImplementedError

    async def get_market_news(self, limit=10):
        raise NotImplementedError

    async def health_check(self):
        return ProviderHealth.HEALTHY

    async def disconnect(self):
        pass


def test_get_quote_reuses_todays_already_ingested_local_bar_instead_of_a_live_call(client, db_session):
    stock = _make_stock(db_session)
    db_session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=datetime.now(timezone.utc),
            open=Decimal("30.0"),
            high=Decimal("31.0"),
            low=Decimal("29.0"),
            close=Decimal("30.5"),
            volume=12345,
            source="sahmk",
            is_synthetic=False,
        )
    )
    db_session.commit()

    import main
    from src.api.dependencies import get_market_provider

    main.app.dependency_overrides[get_market_provider] = lambda: _FailIfCalledProvider()
    try:
        response = client.get("/api/v1/stocks/2222/quote")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["open"] == 30.0
    assert body["high"] == 31.0
    assert body["low"] == 29.0
    assert body["volume"] == 12345
    assert body["close"] == 30.9  # the live quote still wins for `close`, unchanged behavior
    assert body["source"] == "sahmk"
    assert body["is_synthetic"] is False


def test_get_quote_falls_back_to_live_when_the_local_bar_is_not_from_today(client, db_session):
    """A registered Stock with only stale (non-today) bars must still
    fall back to a live provider call -- proves the fix doesn't serve
    outdated open/high/low as if it were current."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=3)  # dated 2026-01-01..03, never "today"

    response = client.get("/api/v1/stocks/2222/quote")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["source"] == "dev-synthetic"


# --- GET /api/v1/stocks/{symbol}/history --------------------------------


def test_get_history_returns_ingested_bars_in_order(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=5)

    response = client.get("/api/v1/stocks/2222/history")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["timeframe"] == "1d"
    assert len(body["bars"]) == 5
    timestamps = [bar["timestamp"] for bar in body["bars"]]
    assert timestamps == sorted(timestamps)


def test_get_history_empty_list_when_nothing_ingested_yet(client, db_session):
    """No bars ingested is a valid state (200 + empty list), not an error."""
    _make_stock(db_session)
    response = client.get("/api/v1/stocks/2222/history")
    assert response.status_code == 200
    assert response.json()["bars"] == []


def test_get_history_respects_date_range(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=10)

    response = client.get(
        "/api/v1/stocks/2222/history",
        params={"start": "2026-01-03T00:00:00Z", "end": "2026-01-05T00:00:00Z"},
    )
    assert response.status_code == 200
    assert len(response.json()["bars"]) == 3


def test_get_history_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/history")
    assert response.status_code == 404


# --- GET /api/v1/stocks/{symbol}/technical ------------------------------


def test_get_technical_analysis_returns_full_indicator_set(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=40)

    response = client.get("/api/v1/stocks/2222/technical")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["bars_used"] == 40
    assert set(body["indicators"]) == {
        "sma_20",
        "ema_20",
        "adx_14",
        "supertrend",
        "rsi_14",
        "macd",
        "stochastic_14_3_3",
        "bollinger",
        "atr_14",
        "obv",
        "volume_sma_20",
        "vwap_20",
        "volume_profile",
        "candlestick_patterns",
        "fibonacci_retracement",
        "support_resistance",
    }


def test_get_technical_analysis_includes_a_real_moving_average_series(client, db_session):
    # Phase 2F (Smart Chart): sma_20/ema_20/vwap_20 are exposed as full
    # per-bar series (not just the single latest() value already in
    # `indicators`) so the chart can draw an actual line overlay.
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=40)

    response = client.get("/api/v1/stocks/2222/technical")
    assert response.status_code == 200
    body = response.json()
    assert set(body["moving_averages"]) == {"sma_20", "ema_20", "vwap_20"}
    sma_series = body["moving_averages"]["sma_20"]
    # A 20-period SMA over 40 bars has no value for the first 19 bars --
    # the real leading NaNs are dropped, not fabricated as zero/None.
    assert len(sma_series) == 21
    assert all("timestamp" in point and "value" in point for point in sma_series)
    assert all(isinstance(point["value"], float) for point in sma_series)


def test_get_technical_analysis_handles_a_moving_average_series_that_is_entirely_empty(client, db_session):
    """Phase 2I: vwap_20 is undefined (NaN) over any window with zero
    total volume -- with zero volume on every bar, the whole series
    drops out via dropna(), leaving an empty list rather than a
    partial one. The response must still serialize cleanly and the
    other two series (which don't depend on volume) stay populated."""
    stock = _make_stock(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(40):
        db_session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=Decimal("30.0") + i * Decimal("0.1"),
                high=Decimal("31.0") + i * Decimal("0.1"),
                low=Decimal("29.0") + i * Decimal("0.1"),
                close=Decimal("30.5") + i * Decimal("0.1"),
                volume=0,
            )
        )
    db_session.commit()

    response = client.get("/api/v1/stocks/2222/technical")
    assert response.status_code == 200
    body = response.json()
    assert body["moving_averages"]["vwap_20"] == []
    assert len(body["moving_averages"]["sma_20"]) == 21
    assert len(body["moving_averages"]["ema_20"]) > 0


def test_get_technical_analysis_422_when_insufficient_history(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=10)  # fewer than the 35-bar minimum

    response = client.get("/api/v1/stocks/2222/technical")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


def test_get_technical_analysis_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/technical")
    assert response.status_code == 404


# --- GET /api/v1/stocks/{symbol}/fundamentals ---------------------------


def test_get_fundamentals_returns_ratios_with_live_valuation(client, db_session):
    stock = _make_stock(db_session)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["period_type"] == "annual"
    assert body["source"] == "dev-synthetic"
    assert body["is_synthetic"] is True
    assert body["ratios"]["net_profit_margin"] == 0.1
    # Valuation ratios need a live price -- confirms the DevMarketDataProvider
    # quote was actually wired in, not just the ratios that need no price.
    assert body["ratios"]["price_to_earnings"] is not None
    assert body["ratios"]["market_cap"] is not None


def test_get_fundamentals_growth_ratios_use_prior_period(client, db_session):
    stock = _make_stock(db_session)
    _add_fundamentals(db_session, stock, fiscal_year=2024, revenue="800000")
    _add_fundamentals(db_session, stock, fiscal_year=2025, revenue="1000000")

    response = client.get("/api/v1/stocks/2222/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["fiscal_period_end"] == "2025-12-31"
    assert body["ratios"]["revenue_growth"] == 0.25  # (1,000,000 - 800,000) / 800,000


def test_get_fundamentals_422_when_none_ingested_yet(client, db_session):
    _make_stock(db_session)
    response = client.get("/api/v1/stocks/2222/fundamentals")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


def test_get_fundamentals_still_succeeds_when_live_price_is_unavailable(client, db_session):
    """A provider outage must not fail the whole endpoint -- only the
    valuation ratios that need a live price become None."""
    stock = _make_stock(db_session)
    _add_fundamentals(db_session, stock)

    import main
    from src.api.dependencies import get_market_provider

    main.app.dependency_overrides[get_market_provider] = lambda: _AlwaysDownProvider()
    try:
        response = client.get("/api/v1/stocks/2222/fundamentals")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["ratios"]["price_to_earnings"] is None
    assert body["ratios"]["net_profit_margin"] == 0.1  # needs no price -- still computed


def test_get_fundamentals_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/fundamentals")
    assert response.status_code == 404


# --- GET /api/v1/stocks/search ------------------------------------------


def test_search_by_exact_symbol(client, db_session):
    _make_stock(db_session)
    response = client.get("/api/v1/stocks/search", params={"q": "2222"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "2222"
    assert [r["symbol"] for r in body["results"]] == ["2222"]


def test_search_by_arabic_name_substring(client, db_session):
    stock = _make_stock(db_session)
    stock.name_ar = "أرامكو السعودية"
    db_session.commit()

    response = client.get("/api/v1/stocks/search", params={"q": "أرامكو"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["symbol"] == "2222"
    assert results[0]["name_ar"] == "أرامكو السعودية"


def test_search_matches_hamza_alef_variant_not_present_in_stored_name(client, db_session):
    """Stored name uses the hamza form (أرامكو); a query typed without
    the hamza (ارامكو) must still match via the normalized-Arabic
    fallback -- a plain SQL ILIKE alone would miss this."""
    stock = _make_stock(db_session)
    stock.name_ar = "أرامكو السعودية"
    db_session.commit()

    response = client.get("/api/v1/stocks/search", params={"q": "ارامكو"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["symbol"] == "2222"


def test_search_matches_despite_extra_internal_whitespace_in_query(client, db_session):
    stock = _make_stock(db_session)
    stock.name_ar = "أرامكو السعودية"
    db_session.commit()

    response = client.get("/api/v1/stocks/search", params={"q": "أرامكو  السعودية"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["symbol"] == "2222"


def test_search_by_english_name_substring_case_insensitive(client, db_session):
    _make_stock(db_session)  # name_en="Saudi Aramco"
    response = client.get("/api/v1/stocks/search", params={"q": "aramco"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["symbol"] == "2222"


def test_search_returns_empty_results_for_no_match(client, db_session):
    _make_stock(db_session)
    response = client.get("/api/v1/stocks/search", params={"q": "nonexistent-xyz"})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_excludes_inactive_stocks(client, db_session):
    stock = _make_stock(db_session)
    stock.is_active = False
    db_session.commit()

    response = client.get("/api/v1/stocks/search", params={"q": "2222"})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_requires_a_query(client, db_session):
    response = client.get("/api/v1/stocks/search")
    assert response.status_code == 422


def test_search_is_registered_before_the_symbol_wildcard_route(client, db_session):
    # If /{symbol} ever swallowed "/search", this would try to look up
    # a stock literally named "search" and 404 instead of returning
    # the search envelope shape.
    response = client.get("/api/v1/stocks/search", params={"q": "x"})
    assert response.status_code == 200
    assert "results" in response.json()


# --- GET /api/v1/stocks/directory (Phase F: All-Stocks) ---------------


def test_directory_is_registered_before_the_symbol_wildcard_route(client, db_session):
    response = client.get("/api/v1/stocks/directory")
    assert response.status_code == 200
    assert "results" in response.json()


def test_directory_lists_active_stocks_with_no_price_yet(client, db_session):
    _make_stock(db_session)
    response = client.get("/api/v1/stocks/directory")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    row = body["results"][0]
    assert row["symbol"] == "2222"
    assert row["current_price"] is None
    assert row["change_amount"] is None
    assert row["change_pct"] is None
    assert row["freshness_label_ar"] == "غير معروف"


def test_directory_computes_current_price_and_change_from_the_two_most_recent_bars(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=3)
    # _add_bars writes close = 30.5, 30.6, 30.7 for days 0,1,2 (ascending
    # by day) -- the two most recent are day2 (30.7, "current") and
    # day1 (30.6, "previous").
    response = client.get("/api/v1/stocks/directory")
    assert response.status_code == 200
    row = response.json()["results"][0]
    assert row["current_price"] == pytest.approx(30.7)
    assert row["change_amount"] == pytest.approx(0.1)
    assert row["change_pct"] == pytest.approx(round((0.1 / 30.6) * 100.0, 4))
    assert row["freshness_label_ar"] == "آخر جلسة"


def test_directory_single_bar_has_price_but_no_change(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=1)
    response = client.get("/api/v1/stocks/directory")
    row = response.json()["results"][0]
    assert row["current_price"] == pytest.approx(30.5)
    assert row["change_amount"] is None
    assert row["change_pct"] is None


def test_directory_excludes_inactive_stocks(client, db_session):
    stock = _make_stock(db_session)
    stock.is_active = False
    db_session.commit()
    response = client.get("/api/v1/stocks/directory")
    assert response.json()["total"] == 0


def test_directory_search_by_arabic_name_matches_the_hamza_variant(client, db_session):
    stock = _make_stock(db_session)
    stock.name_ar = "أرامكو السعودية"
    db_session.commit()
    response = client.get("/api/v1/stocks/directory", params={"q": "ارامكو"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["symbol"] == "2222"


def test_directory_filters_by_sector(client, db_session):
    _make_stock(db_session, symbol="2222")  # sector="Energy"
    other = Stock(symbol="1120", name_en="Al Rajhi Bank", sector="Banks")
    db_session.add(other)
    db_session.commit()

    response = client.get("/api/v1/stocks/directory", params={"sector": "Banks"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["symbol"] for r in results] == ["1120"]


def test_directory_pagination(client, db_session):
    for i in range(5):
        db_session.add(Stock(symbol=f"100{i}", name_en=f"Stock {i}"))
    db_session.commit()

    response = client.get("/api/v1/stocks/directory", params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["results"]) == 2
    assert [r["symbol"] for r in body["results"]] == ["1002", "1003"]


def test_directory_never_calls_the_market_data_provider(client, db_session, monkeypatch):
    """Browsing the All-Stocks directory must be zero-SAHMK -- it only
    ever reads already-persisted PriceBar rows, never the injected
    market-data provider."""
    from main import app
    from src.api.dependencies import get_market_provider

    def _fail_if_called():
        raise AssertionError("get_stock_directory must never resolve a live market-data provider")

    app.dependency_overrides[get_market_provider] = _fail_if_called
    try:
        stock = _make_stock(db_session)
        _add_bars(db_session, stock, count=2)
        response = client.get("/api/v1/stocks/directory")
        assert response.status_code == 200
    finally:
        del app.dependency_overrides[get_market_provider]
