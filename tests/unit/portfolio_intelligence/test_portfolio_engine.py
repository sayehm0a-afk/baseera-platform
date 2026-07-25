"""Unit tests for HoldingAnalyzer and PortfolioEngine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.portfolio_intelligence.portfolio_engine import HoldingAnalyzer, PortfolioEngine
from src.portfolio_intelligence.types import Holding


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


def _seed_stock_with_bars(factory, symbol, sector="Energy", count=80):
    session = factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    for i in range(count):
        price += 0.08
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(price)), high=Decimal(str(price + 0.5)), low=Decimal(str(price - 0.5)),
                close=Decimal(str(price)), volume=1000 + i,
            )
        )
    session.commit()
    session.close()


# --- HoldingAnalyzer -------------------------------------------------------


@pytest.mark.asyncio
async def test_holding_analyzer_symbol_not_registered(factory):
    session = factory()
    analyzer = HoldingAnalyzer(session, DevMarketDataProvider())
    results = await analyzer.analyze([Holding(symbol="9999", quantity=10)])
    session.close()

    assert results[0].report is None
    assert results[0].error == "symbol not registered"
    assert results[0].market_value is None


@pytest.mark.asyncio
async def test_holding_analyzer_insufficient_data(factory):
    session = factory()
    session.add(Stock(symbol="2222", name_en="Stock 2222", sector="Energy"))
    session.commit()
    analyzer = HoldingAnalyzer(session, DevMarketDataProvider())
    results = await analyzer.analyze([Holding(symbol="2222", quantity=10)])
    session.close()

    assert results[0].report is None
    assert results[0].error is None  # honest skip, not a failure


@pytest.mark.asyncio
async def test_holding_analyzer_computes_market_value_and_pnl(factory):
    _seed_stock_with_bars(factory, "2222")
    session = factory()
    analyzer = HoldingAnalyzer(session, DevMarketDataProvider())
    results = await analyzer.analyze([Holding(symbol="2222", quantity=10, average_cost=20.0)])
    session.close()

    holding = results[0]
    assert holding.report is not None
    assert holding.latest_price is not None
    assert holding.market_value == holding.quantity * holding.latest_price
    assert holding.unrealized_pnl == holding.market_value - (10 * 20.0)


@pytest.mark.asyncio
async def test_holding_analyzer_isolates_one_symbols_failure(factory, monkeypatch):
    _seed_stock_with_bars(factory, "2222")
    _seed_stock_with_bars(factory, "1010", sector="Banks")
    session = factory()

    analyzer = HoldingAnalyzer(session, DevMarketDataProvider())
    original_analyze = analyzer._analyst_engine.analyze

    async def _broken_analyze(context):
        if context.symbol == "1010":
            raise RuntimeError("boom")
        return await original_analyze(context)

    analyzer._analyst_engine.analyze = _broken_analyze

    results = await analyzer.analyze([Holding(symbol="2222", quantity=10), Holding(symbol="1010", quantity=5)])
    session.close()

    by_symbol = {r.symbol: r for r in results}
    assert by_symbol["1010"].error == "boom"


# --- PortfolioEngine --------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_engine_full_analysis(factory):
    _seed_stock_with_bars(factory, "2222", sector="Energy")
    _seed_stock_with_bars(factory, "1010", sector="Banks")
    session = factory()

    engine = PortfolioEngine(session, DevMarketDataProvider())
    holdings = [Holding(symbol="2222", quantity=100, average_cost=30.0), Holding(symbol="1010", quantity=50, average_cost=28.0)]
    analysis = await engine.analyze(portfolio_id=1, name="Test", holdings=holdings, cash=1000.0)
    session.close()

    assert analysis.total_value > 0
    assert len(analysis.holdings) == 2
    assert all(h.weight is not None for h in analysis.holdings)
    total_weight = sum(h.weight for h in analysis.holdings) + analysis.allocation.cash_weight
    assert abs(total_weight - 1.0) < 1e-6
    assert analysis.health_score.score >= 0
    assert analysis.risk_profile.risk_score >= 0
    assert len(analysis.sector_exposure) == 2
    assert analysis.recommendations.cash_recommendation is not None
