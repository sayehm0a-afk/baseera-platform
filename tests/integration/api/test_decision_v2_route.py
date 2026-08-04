"""Integration tests for GET /api/v1/stocks/{symbol}/decision-v2 --
real FastAPI routing, real dependency injection, the real
TechnicalAnalysisEngine/RecommendationEngine/AIDecisionEngine/
DecisionEngineV2 pipeline, against an in-memory SQLite DB and Dev*
providers (see conftest.py). No live network call anywhere.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

import pytest

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import DecisionV2Snapshot, FundamentalSnapshot, PeriodType, PriceBar, Stock, Timeframe
from src.market_data.providers.market_data_provider import IMarketDataProvider, ProviderHealth


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    """Every /api/v1/stocks/* route requires require_active_subscription()
    (Phase 13 P13.5) -- see conftest.py's authenticated_as_staff."""


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
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _add_bars(session: Session, stock: Stock, count: int, uptrend: bool = True) -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        step = Decimal("0.1") * i if uptrend else Decimal("0.0")
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


_VALID_DECISIONS = {
    "STRONG_BUY_CANDIDATE", "BUY_CANDIDATE", "WAIT_FOR_ENTRY", "WATCH",
    "HOLD", "REDUCE", "EXIT", "REJECT", "INSUFFICIENT_DATA",
}
_VALID_FRESHNESS = {"LIVE", "LAST_SESSION", "STALE", "UNKNOWN"}


def test_decision_v2_with_both_legs_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "2222"
    assert body["company_name_ar"] == "أرامكو السعودية"
    assert body["company_name_en"] == "Saudi Aramco"
    assert body["sector_ar"] == "الطاقة"
    assert body["decision"] in _VALID_DECISIONS
    assert body["decision_label_ar"]
    assert 0.0 <= body["confidence_score"] <= 100.0
    assert body["confidence_disclaimer_ar"] == (
        "درجة الثقة تقيس قوة وتوافق الأدلة المتاحة، ولا تعني ضمان تحقق الهدف."
    )
    assert body["analysis_disclaimer_ar"].startswith("هذا تحليل آلي مساعد")
    assert 0.0 <= body["opportunity_quality_score"] <= 100.0
    assert 0.0 <= body["risk_score"] <= 100.0
    assert body["data_freshness_status"] in _VALID_FRESHNESS
    assert body["analysis_version"] == "2.0.0"
    assert body["data_source"]
    assert isinstance(body["sub_scores"], dict)
    assert isinstance(body["gates"], list) and len(body["gates"]) > 0
    for gate in body["gates"]:
        assert {"name", "passed", "detail", "blocking"} <= gate.keys()

    # A best-effort DecisionV2Snapshot row should have been inserted.
    # (The test fixture's staff user is an in-memory, never-persisted
    # User -- see authenticated_as_staff's own docstring -- so its id is
    # None and requested_by_user_id is correctly null here; a real
    # session would have a real id.)
    rows = db_session.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.symbol == "2222").all()
    assert len(rows) == 1
    assert rows[0].decision == body["decision"]


_VALID_ENTRY_STATUSES = {
    "READY_NOW", "NEAR_ENTRY", "WAIT_FOR_PULLBACK", "MISSED_ENTRY",
    "CONDITIONAL_ON_BREAKOUT", "NOT_SUITABLE",
}
_VALID_TRADE_TYPES = {
    "SCALP", "INTRADAY", "SHORT_SWING_2_5_DAYS", "WEEKLY_SWING", "SWING_TRADE",
    "MONTHLY_INVESTMENT", "MEDIUM_TERM_INVESTMENT", "LONG_TERM_INVESTMENT",
}


def test_decision_v2_response_includes_the_phase_2a_canonical_fields(client, db_session):
    """Phase 2A: the response must carry the full canonical stock-
    intelligence output (trade type, price plan, support/resistance,
    liquidity/accumulation, confidence breakdown, Arabic reasoning),
    not just the Phase 1 subset."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["is_real_data"], bool)
    assert body["entry_status"] in _VALID_ENTRY_STATUSES
    assert body["entry_status_label_ar"]
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
    assert body["risk_level_label_ar"]
    assert body["entry_quality"] in {"POOR", "FAIR", "GOOD", "EXCELLENT"}
    assert body["entry_quality_label_ar"]
    if body["trade_type"] is not None:
        assert body["trade_type"] in _VALID_TRADE_TYPES
        assert body["trade_type"] not in ("SCALP", "INTRADAY")
    assert isinstance(body["technical_evidence"], dict)
    assert len(body["technical_evidence"]) > 0
    assert body["decision_summary_ar"]
    assert body["why_now_ar"]
    assert body["why_not_stronger_ar"]
    assert isinstance(body["entry_confirmation_conditions_ar"], list)
    assert isinstance(body["watch_next_session_ar"], list)
    assert body["accumulation_score"] == body["sub_scores"]["volume_score"]
    assert body["technical_confidence"] == body["sub_scores"]["trend_score"]


def test_decision_v2_never_shows_strong_buy_without_gates_passing(client, db_session):
    """A clearly-uptrending, fully-available-data symbol may legitimately
    reach STRONG_BUY_CANDIDATE/BUY_CANDIDATE -- but only via the real gate
    cascade, never bypassing it. This just asserts internal consistency:
    an actionable buy-side decision always carries a valid entry zone and
    stop below it, per gates.py's own invariants."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=90, uptrend=True)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    if body["decision"] in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"):
        assert body["entry_zone_low"] is not None and body["entry_zone_high"] is not None
        assert body["entry_zone_low"] <= body["entry_zone_high"]
        assert body["stop_loss"] is not None and body["stop_loss"] < body["entry_zone_low"]
        assert body["target_1"] is not None and body["target_1"] > body["entry_zone_high"]


def test_decision_v2_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/decision-v2")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stock_not_found"


def test_decision_v2_422_when_neither_leg_available(client, db_session):
    _make_stock(db_session)  # no bars, no fundamentals ingested

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


def test_decision_v2_degrades_when_provider_is_down_but_technical_data_exists(client, db_session):
    import main
    from src.api.dependencies import get_market_provider

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)

    main.app.dependency_overrides[get_market_provider] = lambda: _AlwaysDownProvider()
    try:
        response = client.get("/api/v1/stocks/2222/decision-v2")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in _VALID_DECISIONS


def test_decision_v2_response_never_exposes_credentials(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    body_text = response.text.lower()
    assert "sahmk_api_key" not in body_text
    assert "shmk_" not in body_text
