"""Unit tests for SymbolSelector."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.market_intelligence.symbol_selector import SymbolSelector


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _add_stock(session, symbol, is_active=True, with_bars=False):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", is_active=is_active)
    session.add(stock)
    session.commit()
    if with_bars:
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=datetime.now(timezone.utc) - timedelta(days=1),
                open=Decimal("10"), high=Decimal("11"), low=Decimal("9"), close=Decimal("10.5"), volume=1000,
            )
        )
        session.commit()
    return stock


def test_select_returns_only_active_symbols_with_price_history(session, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "true")
    _add_stock(session, "1010", is_active=True, with_bars=True)
    _add_stock(session, "2222", is_active=True, with_bars=False)  # no bars -> skipped
    _add_stock(session, "3333", is_active=False, with_bars=True)  # inactive -> skipped

    symbols = SymbolSelector().select(session)

    assert symbols == ["1010"]


def test_select_includes_symbols_without_price_history_when_not_required(session, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "false")
    _add_stock(session, "1010", is_active=True, with_bars=True)
    _add_stock(session, "2222", is_active=True, with_bars=False)

    symbols = SymbolSelector().select(session)

    assert symbols == ["1010", "2222"]


def test_select_results_are_alphabetically_ordered(session):
    _add_stock(session, "3333", with_bars=True)
    _add_stock(session, "1111", with_bars=True)
    _add_stock(session, "2222", with_bars=True)

    assert SymbolSelector().select(session) == ["1111", "2222", "3333"]


def test_explicit_symbols_bypass_discovery_entirely(session):
    _add_stock(session, "1010", with_bars=True)

    symbols = SymbolSelector().select(session, symbols=["9999", "8888"])

    assert symbols == ["9999", "8888"]


def test_select_truncates_to_max_symbols(session, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_MAX_SYMBOLS", "2")
    for symbol in ("1111", "2222", "3333"):
        _add_stock(session, symbol, with_bars=True)

    symbols = SymbolSelector().select(session)

    assert len(symbols) == 2
    assert symbols == ["1111", "2222"]
