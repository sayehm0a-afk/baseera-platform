"""Integration tests for GET /api/v1/stocks/{symbol}/recommendation --
real FastAPI routing, real dependency injection, real
TechnicalAnalysisEngine/FundamentalAnalysisEngine/RecommendationEngine,
against an in-memory SQLite DB and Dev* providers (see conftest.py).
No live network call anywhere.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import FundamentalSnapshot, PeriodType, PriceBar, Stock, Timeframe
from src.market_data.providers.market_data_provider import IMarketDataProvider, ProviderHealth


class _AlwaysDownProvider(IMarketDataProvider):
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


def _add_bars(session: Session, stock: Stock, count: int, trend: str = "up") -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        step = Decimal("0.1") * i if trend == "up" else Decimal("-0.05") * i
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=Decimal("30.0") + step,
                high=Decimal("31.0") + step,
                low=Decimal("29.0") + step,
                close=Decimal("30.5") + step,
                volume=1000 + i,
            )
        )
    session.commit()


def _add_fundamentals(session: Session, stock: Stock, fiscal_year: int = 2025) -> None:
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=date(fiscal_year, 12, 31),
            revenue=Decimal("1000000"),
            net_income=Decimal("150000"),
            total_assets=Decimal("2000000"),
            total_liabilities=Decimal("700000"),
            total_equity=Decimal("1300000"),
            current_assets=Decimal("900000"),
            current_liabilities=Decimal("400000"),
            shares_outstanding=1_000_000,
            eps=Decimal("0.15"),
            dividend_per_share=Decimal("0.02"),
            source="dev-synthetic",
            is_synthetic=True,
        )
    )
    session.commit()


# --- happy path --------------------------------------------------------


def test_recommendation_with_both_legs_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/recommendation")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "2222"
    assert body["recommendation"] in {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    assert 0.0 <= body["confidence"] <= 100.0
    assert 0.0 <= body["final_score"] <= 100.0
    assert body["technical_score"] is not None
    assert body["fundamental_score"] is not None
    assert isinstance(body["explanation"], str) and len(body["explanation"]) > 0
    assert "2222" in body["explanation"]

    sources = {c["source"] for c in body["contributions"]}
    assert sources == {"technical", "fundamental"}
    assert len(body["signals"]) > 0
    for signal in body["signals"]:
        assert signal["direction"] in {"bullish", "bearish", "neutral"}
        assert signal["source"] in {"technical", "fundamental"}


def test_recommendation_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/recommendation")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stock_not_found"


# --- graceful degradation: only one leg available --------------------------


def test_recommendation_with_only_technical_leg_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    # No fundamentals ingested.

    response = client.get("/api/v1/stocks/2222/recommendation")
    assert response.status_code == 200
    body = response.json()

    assert body["technical_score"] is not None
    assert body["fundamental_score"] is None
    fundamental_contribution = next(c for c in body["contributions"] if c["source"] == "fundamental")
    assert fundamental_contribution["score"] is None
    assert "fundamental" in body["explanation"].lower()


def test_recommendation_with_only_fundamental_leg_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=5)  # below the 35-bar technical minimum
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/recommendation")
    assert response.status_code == 200
    body = response.json()

    assert body["technical_score"] is None
    assert body["fundamental_score"] is not None
    technical_contribution = next(c for c in body["contributions"] if c["source"] == "technical")
    assert technical_contribution["score"] is None


def test_recommendation_422_when_neither_leg_available(client, db_session):
    _make_stock(db_session)  # no bars, no fundamentals ingested

    response = client.get("/api/v1/stocks/2222/recommendation")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


# --- graceful degradation: market data provider outage ---------------------


def test_recommendation_degrades_valuation_ratios_when_provider_is_down(client, db_session):
    """A provider outage must only drop the market-price-dependent
    valuation ratios (P/E, P/B) -- it must not fail the whole
    recommendation, exactly like /fundamentals already behaves."""
    import main
    from src.api.dependencies import get_market_provider

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    main.app.dependency_overrides[get_market_provider] = lambda: _AlwaysDownProvider()
    try:
        response = client.get("/api/v1/stocks/2222/recommendation")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["technical_score"] is not None
    assert body["fundamental_score"] is not None
    assert not any(s["name"] in ("price_to_earnings", "price_to_book") for s in body["signals"])
