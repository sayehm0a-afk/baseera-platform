"""Unit tests for build_analysis_context -- extracted from
src/api/routes/stocks.py's former _build_analysis_context so it can be
reused by src.market_intelligence without duplicating this assembly
logic. Behavior is unchanged from before the extraction (covered
end-to-end by tests/integration/api/test_decision_route.py,
test_recommendation_route.py, test_analyst_report_route.py); these
tests exercise the function directly, against an in-memory SQLite DB
and the Dev* providers, with no REST layer involved.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.context_builder import build_analysis_context
from src.core.db.database import Base
from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import (
    FundamentalSnapshot,
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    PeriodType,
    PriceBar,
    SentimentLabel,
    Stock,
    Timeframe,
)
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider, ProviderHealth
from src.news_intelligence.service import NewsIntelligenceService


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


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _make_stock(session, symbol="2222") -> Stock:
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _add_bars(session, stock, count=60):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        step = Decimal("0.1") * i
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal("30.0") + step, high=Decimal("31.0") + step, low=Decimal("29.0") + step,
                close=Decimal("30.5") + step, volume=1000 + i,
            )
        )
    session.commit()


def _add_fundamentals(session, stock, fiscal_year=2025):
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id, period_type=PeriodType.ANNUAL, fiscal_period_end=date(fiscal_year, 12, 31),
            revenue=Decimal("1000000"), net_income=Decimal("150000"), total_assets=Decimal("2000000"),
            total_liabilities=Decimal("700000"), total_equity=Decimal("1300000"),
            current_assets=Decimal("900000"), current_liabilities=Decimal("400000"),
            shares_outstanding=1_000_000, eps=Decimal("0.15"), dividend_per_share=Decimal("0.02"),
            source="dev-synthetic", is_synthetic=True,
        )
    )
    session.commit()


@pytest.mark.asyncio
async def test_both_legs_available(session):
    stock = _make_stock(session)
    _add_bars(session, stock)
    _add_fundamentals(session, stock)

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())

    assert context.symbol == "2222"
    assert context.technical_result is not None
    assert context.fundamental_result is not None
    assert context.latest_price is not None


@pytest.mark.asyncio
async def test_no_data_yields_both_legs_none(session):
    stock = _make_stock(session)  # no bars, no fundamentals ingested

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())

    assert context.technical_result is None
    assert context.fundamental_result is None


@pytest.mark.asyncio
async def test_degrades_gracefully_when_provider_is_down(session):
    stock = _make_stock(session)
    _add_bars(session, stock)

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, _AlwaysDownProvider())

    assert context.technical_result is not None
    assert context.latest_price is None


@pytest.mark.asyncio
async def test_no_news_leaves_extra_empty(session):
    stock = _make_stock(session)
    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())
    assert context.extra == {}


@pytest.mark.asyncio
async def test_real_persisted_news_populates_extra_news_sentiment(session):
    # This is the exact mechanism behind "the recommendation must
    # automatically change when important news appears" (Phase 12,
    # requirement 8): build_analysis_context is the one hook point
    # every consumer (routes, portfolio, market scanner) shares, and a
    # NewsEvent persisted by the News Intelligence Engine flows through
    # it with zero changes anywhere else.
    stock = _make_stock(session)
    event = NewsEvent(
        external_key="test-key-1", headline="Saudi Aramco reports record quarterly profit", source="sahmk",
        source_reliability_score=0.8, published_at=datetime.now(timezone.utc), is_synthetic=False,
        category=NewsCategory.EARNINGS, sentiment_score=0.7, sentiment_label=SentimentLabel.POSITIVE,
        confidence=85.0, explanation="Strong profit beat.", analyzed_at=datetime.now(timezone.utc),
        analysis_model="gpt-4o-mini",
    )
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, stock_id=stock.id, symbol="2222"))
    session.commit()

    context = await build_analysis_context(
        stock, PeriodType.ANNUAL, session, DevMarketDataProvider(), news_service=NewsIntelligenceService()
    )

    assert "news_sentiment" in context.extra
    assert context.extra["news_sentiment"]["sentiment_score"] == pytest.approx(0.7)
    assert context.extra["news_sentiment"]["article_count"] == 1
    assert context.extra["news_sentiment"]["events"][0]["headline"] == "Saudi Aramco reports record quarterly profit"
