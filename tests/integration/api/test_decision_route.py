"""Integration tests for GET /api/v1/stocks/{symbol}/decision -- real
FastAPI routing, real dependency injection, real
TechnicalAnalysisEngine/FundamentalAnalysisEngine/RecommendationEngine/
AIDecisionEngine, against an in-memory SQLite DB and Dev* providers
(see conftest.py). No live network call anywhere.
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


def _add_bars(session: Session, stock: Stock, count: int) -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        step = Decimal("0.1") * i
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


_VALID_RECOMMENDATIONS = {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
_VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
_VALID_TIME_HORIZONS = {"SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"}
_VALID_POSITION_SIZES = {"NONE", "SMALL", "MODERATE", "STANDARD", "LARGE"}


# --- happy path ----------------------------------------------------------


def test_decision_with_both_legs_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "2222"
    assert body["recommendation"] in _VALID_RECOMMENDATIONS
    assert 0.0 <= body["confidence"] <= 100.0
    assert 0.0 <= body["final_score"] <= 100.0
    assert body["risk_level"] in _VALID_RISK_LEVELS
    assert body["time_horizon"] in _VALID_TIME_HORIZONS
    assert body["position_size"] in _VALID_POSITION_SIZES
    assert isinstance(body["reasons"], list) and len(body["reasons"]) > 0
    assert any("2222" in r for r in body["reasons"])

    # a real price was ingested/quoted -> target price and stop loss should be present.
    assert body["target_price"] is not None
    assert body["stop_loss"] is not None
    assert body["expected_return_pct"] is not None

    categories = {b["category"] for b in body["breakdown"]}
    assert categories == {
        "Technical Analysis", "Fundamental Analysis", "Momentum", "Volume", "Risk",
        "Price Structure", "Value Area",
        "News", "Macro", "Insider Transactions", "Sector Rotation",
    }
    for b in body["breakdown"]:
        assert "points" in b and "weight" in b and "confidence" in b and "available" in b

    assert len(body["signals"]) > 0
    for signal in body["signals"]:
        assert signal["direction"] in {"bullish", "bearish", "neutral"}


def test_decision_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/decision")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stock_not_found"


def test_decision_422_when_neither_leg_available(client, db_session):
    _make_stock(db_session)  # no bars, no fundamentals ingested

    response = client.get("/api/v1/stocks/2222/decision")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


# --- graceful degradation ------------------------------------------------


def test_decision_with_only_technical_leg_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)

    response = client.get("/api/v1/stocks/2222/decision")
    assert response.status_code == 200
    body = response.json()
    fundamental_contribution = next(b for b in body["breakdown"] if b["category"] == "Fundamental Analysis")
    assert fundamental_contribution["available"] is False
    # a live Dev quote is still available -> target price should still be computed.
    assert body["target_price"] is not None


def test_decision_degrades_when_provider_is_down_but_technical_data_exists(client, db_session):
    """A provider outage must not fail the whole decision -- it only
    means no live price (so no target/stop loss/expected return) and
    no valuation ratios, exactly like /recommendation already behaves."""
    import main
    from src.api.dependencies import get_market_provider

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)

    main.app.dependency_overrides[get_market_provider] = lambda: _AlwaysDownProvider()
    try:
        response = client.get("/api/v1/stocks/2222/decision")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    # Technical analysis alone still anchors a price via Bollinger's middle band.
    assert body["recommendation"] in _VALID_RECOMMENDATIONS


# --- extra-bag pluggability through the real HTTP boundary -----------------


def test_decision_response_never_exposes_credentials(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision")
    body_text = response.text.lower()
    assert "sahmk_api_key" not in body_text
    assert "shmk_" not in body_text
