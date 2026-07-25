"""Integration tests for GET /api/v1/stocks/{symbol}/analyst-report --
real FastAPI routing, real dependency injection, real
TechnicalAnalysisEngine/FundamentalAnalysisEngine/RecommendationEngine/
AIDecisionEngine/AnalystEngine, against an in-memory SQLite DB and
Dev* providers (see conftest.py). No live network call anywhere, and
no LLM adapter is wired into this route -- every field returned here
comes from the deterministic pipeline.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.domain.models import FundamentalSnapshot, PeriodType, PriceBar, Stock, Timeframe

_VALID_RECOMMENDATIONS = {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
_VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
_VALID_TIME_HORIZONS = {"SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"}
_VALID_POSITION_SIZES = {"NONE", "SMALL", "MODERATE", "STANDARD", "LARGE"}

_EXPLANATION_STRING_FIELDS = [
    "investment_summary",
    "technical_reasoning",
    "fundamental_reasoning",
    "risk_explanation",
    "confidence_explanation",
    "target_price_explanation",
    "stop_loss_explanation",
    "time_horizon_explanation",
    "final_recommendation_rationale",
]
_EXPLANATION_LIST_FIELDS = ["bullish_factors", "bearish_factors", "alternative_scenarios"]


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


# --- happy path (JSON) -----------------------------------------------------


def test_analyst_report_json_with_both_legs_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/analyst-report")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "2222"
    assert body["recommendation"] in _VALID_RECOMMENDATIONS
    assert 0.0 <= body["confidence"] <= 100.0
    assert body["risk_level"] in _VALID_RISK_LEVELS
    assert body["time_horizon"] in _VALID_TIME_HORIZONS
    assert body["position_size"] in _VALID_POSITION_SIZES
    assert body["engine_version"]
    assert body["generated_at"]

    for field in _EXPLANATION_STRING_FIELDS:
        assert isinstance(body[field], str) and body[field], field
    for field in _EXPLANATION_LIST_FIELDS:
        assert isinstance(body[field], list), field

    # a real price was ingested/quoted -> target/stop loss explanations should cite it.
    assert body["target_price"] is not None
    assert "could not be computed" not in body["target_price_explanation"]


def test_analyst_report_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/analyst-report")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stock_not_found"


def test_analyst_report_422_when_neither_leg_available(client, db_session):
    _make_stock(db_session)  # no bars, no fundamentals ingested

    response = client.get("/api/v1/stocks/2222/analyst-report")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


# --- graceful degradation ---------------------------------------------------


def test_analyst_report_technical_only_discloses_unavailable_fundamentals(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)

    response = client.get("/api/v1/stocks/2222/analyst-report")
    assert response.status_code == 200
    body = response.json()
    assert "could not be produced" in body["fundamental_reasoning"]
    assert "no ingested financial statements" in body["fundamental_reasoning"]


# --- alternate formats -------------------------------------------------------


def test_analyst_report_markdown_format(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/analyst-report", params={"format": "markdown"})
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert response.text.startswith("# Analyst Report: 2222")
    assert "## Investment Summary" in response.text


def test_analyst_report_text_format(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/analyst-report", params={"format": "text"})
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "ANALYST REPORT: 2222" in response.text


def test_analyst_report_rejects_invalid_format(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)

    response = client.get("/api/v1/stocks/2222/analyst-report", params={"format": "xml"})
    assert response.status_code == 422


# --- security / honesty ------------------------------------------------------


def test_analyst_report_never_exposes_credentials(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/analyst-report")
    body_text = response.text.lower()
    assert "sahmk_api_key" not in body_text
    assert "shmk_" not in body_text
