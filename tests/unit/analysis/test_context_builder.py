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
from src.market_data.sahmk.rate_limiter import SahmkUpstreamQuotaExhaustedError
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


class _LiveQuoteProvider(DevMarketDataProvider):
    """Simulates SahmkMarketDataProvider's real shape: get_stock_data()
    returns a stale completed daily bar, get_latest_quote() (not part of
    IMarketDataProvider) returns the true live price. Used to prove
    build_analysis_context() prefers the live quote during market hours
    instead of the stale daily-bar close."""

    async def get_stock_data(self, symbol):
        bar = await super().get_stock_data(symbol)
        bar["close"] = 999.99  # deliberately distinct from the live quote price below
        return bar

    async def get_latest_quote(self, symbol):
        return {
            "symbol": symbol,
            "price": 42.5,
            "change": 0.5,
            "change_percent": 1.19,
            "volume": 12345,
            "timestamp": "2026-07-29T11:00:00+03:00",
            "source": "sahmk",
            "is_synthetic": False,
        }


class _QuoteFailsButBarWorksProvider(DevMarketDataProvider):
    """get_latest_quote exists but errors (e.g. circuit breaker open) --
    must fall back to the daily-bar close, not leave the price as None."""

    async def get_latest_quote(self, symbol):
        raise CircuitBreakerOpenError()


class _QuoteFailsWithUpstreamQuotaExhaustionProvider(DevMarketDataProvider):
    """get_latest_quote fails with the rate limiter's own preemptive
    block (SahmkUpstreamQuotaExhaustedError, raised by acquire() before
    any network call -- see rate_limiter.py) rather than a SahmkError
    from a failed request. Reproduces a real 2026-08-11 production
    condition: a market scan run while SAHMK's daily quota is confirmed
    exhausted must still fall back to the daily-bar close for every
    symbol, not propagate an uncaught exception that a scan's retry loop
    then futilely retries before failing the whole symbol (losing the
    fundamental leg too, since that never gets a chance to run)."""

    async def get_latest_quote(self, symbol):
        raise SahmkUpstreamQuotaExhaustedError(
            "SAHMK's real daily quota is confirmed exhausted.",
            reset_at_utc=datetime(2026, 8, 11, 21, 0, 0, tzinfo=timezone.utc),
            evidence="Daily rate limit exceeded (5000 requests/day).",
        )


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
async def test_no_news_leaves_extra_with_only_quote_provenance(session):
    # DevMarketDataProvider has no get_latest_quote, so the fallback
    # get_stock_data() leg runs and populates "quote" with the daily
    # bar's own source/is_synthetic/timestamp (needed by Decision Engine
    # V2's freshness/authenticity gates) -- "news_sentiment" stays
    # absent since no NewsEvent was persisted. "bars_used"/
    # "likely_suspended"/"ohlcv_latest_bar_age_days" are always present
    # (the min_candles/suspension/ohlcv_staleness publication gates'
    # real signals) -- no bars were ingested for this stock, so
    # bars_used is 0, likely_suspended is None (not enough history to
    # judge either way), and ohlcv_latest_bar_age_days is None (no bar
    # to measure the age of).
    stock = _make_stock(session)
    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())
    assert set(context.extra.keys()) == {"quote", "bars_used", "likely_suspended", "ohlcv_latest_bar_age_days"}
    assert context.extra["quote"]["source"] == "dev-synthetic"
    assert context.extra["quote"]["is_synthetic"] is True
    assert context.extra["bars_used"] == 0
    assert context.extra["likely_suspended"] is None
    assert context.extra["ohlcv_latest_bar_age_days"] is None
    assert "news_sentiment" not in context.extra


@pytest.mark.asyncio
async def test_live_quote_is_preferred_over_stale_daily_bar(session):
    stock = _make_stock(session)
    _add_bars(session, stock)

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, _LiveQuoteProvider())

    assert context.latest_price == pytest.approx(42.5)
    assert context.extra["quote"]["price"] == pytest.approx(42.5)
    assert context.extra["quote"]["change"] == pytest.approx(0.5)
    assert context.extra["quote"]["change_percent"] == pytest.approx(1.19)
    assert context.extra["quote"]["timestamp"] == "2026-07-29T11:00:00+03:00"
    assert context.extra["quote"]["source"] == "sahmk"


@pytest.mark.asyncio
async def test_falls_back_to_daily_bar_when_live_quote_fails(session):
    stock = _make_stock(session)
    _add_bars(session, stock)

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, _QuoteFailsButBarWorksProvider())

    assert context.latest_price is not None
    assert context.extra["quote"]["source"] == "dev-synthetic"


@pytest.mark.asyncio
async def test_falls_back_to_daily_bar_when_live_quote_hits_upstream_quota_exhaustion(session):
    # Real 2026-08-11 production condition: SahmkUpstreamQuotaExhaustedError
    # is not a SahmkError (it's raised by the rate limiter's own
    # preemptive check, a different exception hierarchy) -- must still
    # be caught here and fall back to the daily bar, not propagate and
    # cost the fundamental leg too.
    stock = _make_stock(session)
    _add_bars(session, stock)

    context = await build_analysis_context(
        stock, PeriodType.ANNUAL, session, _QuoteFailsWithUpstreamQuotaExhaustionProvider()
    )

    assert context.latest_price is not None
    assert context.extra["quote"]["source"] == "dev-synthetic"
    # The technical leg (computed before the quote fetch) must survive
    # the quote failure too -- proof the exception didn't abort the
    # whole function before this leg's result could be returned.
    assert context.technical_result is not None


@pytest.mark.asyncio
async def test_provider_without_live_quote_support_uses_daily_bar(session):
    # DevMarketDataProvider has no get_latest_quote at all -- getattr()
    # must return None and fall through to the existing get_stock_data path.
    stock = _make_stock(session)
    _add_bars(session, stock)

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())

    assert context.latest_price is not None
    assert context.extra["quote"]["source"] == "dev-synthetic"


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


# --- ohlcv_latest_bar_age_days: distinct from quote/scan freshness --------
# The production incident this closes: a live quote is always fetched
# fresh regardless of ingestion health, so it says nothing about
# whether the daily-bar history technical indicators are computed from
# has actually kept up. See src.market_intelligence.publication_gate's
# _ohlcv_staleness_gate, which reads this field.


@pytest.mark.asyncio
async def test_ohlcv_latest_bar_age_is_none_with_no_bar_history(session):
    stock = _make_stock(session)  # no bars ingested

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())

    assert context.extra["ohlcv_latest_bar_age_days"] is None


@pytest.mark.asyncio
async def test_ohlcv_latest_bar_age_reflects_a_recent_bar(session):
    stock = _make_stock(session)
    session.add(
        PriceBar(
            stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=6),
            open=Decimal("30.0"), high=Decimal("31.0"), low=Decimal("29.0"),
            close=Decimal("30.5"), volume=1000,
        )
    )
    session.commit()

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())

    age = context.extra["ohlcv_latest_bar_age_days"]
    assert age is not None
    assert 0.0 <= age < 1.0


@pytest.mark.asyncio
async def test_ohlcv_latest_bar_age_reflects_a_stale_bar(session):
    stock = _make_stock(session)
    session.add(
        PriceBar(
            stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
            timestamp=datetime.now(timezone.utc) - timedelta(days=10),
            open=Decimal("30.0"), high=Decimal("31.0"), low=Decimal("29.0"),
            close=Decimal("30.5"), volume=1000,
        )
    )
    session.commit()

    context = await build_analysis_context(stock, PeriodType.ANNUAL, session, DevMarketDataProvider())

    age = context.extra["ohlcv_latest_bar_age_days"]
    assert age is not None
    assert 9.5 < age < 10.5
