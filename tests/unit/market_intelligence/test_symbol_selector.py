"""Unit tests for SymbolSelector."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import MarketScanRun, MarketScanStatus, PriceBar, RecommendationLabel, Stock, SymbolIntelligenceRecord, Timeframe
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


def _record_evaluation(session, stock, evaluated_at):
    """Minimal SymbolIntelligenceRecord row -- only the columns
    `prioritize_stale`'s staleness ordering reads (`stock_id`,
    `evaluated_at`) matter for these tests; the rest are just whatever
    satisfies the model's non-nullable columns."""
    run = MarketScanRun(status=MarketScanStatus.SUCCESS, symbols_requested=1)
    session.add(run)
    session.commit()
    session.add(
        SymbolIntelligenceRecord(
            scan_run_id=run.id,
            stock_id=stock.id,
            symbol=stock.symbol,
            recommendation=RecommendationLabel.HOLD,
            confidence=Decimal("50"),
            final_score=Decimal("50"),
            evaluated_at=evaluated_at,
            engine_version="test",
        )
    )
    session.commit()


def test_select_with_limit_truncates_regardless_of_universe_size(session):
    for symbol in ("1111", "2222", "3333"):
        _add_stock(session, symbol, with_bars=True)

    symbols = SymbolSelector().select(session, limit=2)

    assert symbols == ["1111", "2222"]


def test_prioritize_stale_puts_never_evaluated_symbols_first(session):
    """A symbol with zero SymbolIntelligenceRecord rows (never
    scanned) must sort ahead of any symbol with a real evaluated_at
    timestamp -- this is the Postgres-vs-SQLite NULLS ordering fix:
    Postgres's ASC default puts NULL last, which would silently starve
    never-scanned symbols in production without the explicit
    nullsfirst() the implementation uses."""
    stale = _add_stock(session, "1111", with_bars=True)
    fresh = _add_stock(session, "2222", with_bars=True)
    never_scanned = _add_stock(session, "3333", with_bars=True)

    now = datetime.now(timezone.utc)
    _record_evaluation(session, stale, now - timedelta(days=2))
    _record_evaluation(session, fresh, now - timedelta(minutes=5))

    symbols = SymbolSelector().select(session, prioritize_stale=True)

    assert symbols[0] == never_scanned.symbol
    assert symbols == ["3333", "1111", "2222"]


def test_prioritize_stale_uses_most_recent_evaluation_per_symbol(session):
    """A symbol evaluated twice must be ordered by its MOST RECENT
    evaluation, not its oldest -- otherwise a symbol that was actually
    just refreshed would incorrectly be treated as still stale."""
    symbol_a = _add_stock(session, "1111", with_bars=True)
    symbol_b = _add_stock(session, "2222", with_bars=True)

    now = datetime.now(timezone.utc)
    _record_evaluation(session, symbol_a, now - timedelta(days=5))
    _record_evaluation(session, symbol_a, now - timedelta(minutes=1))  # just refreshed
    _record_evaluation(session, symbol_b, now - timedelta(hours=1))  # staler than A's latest

    symbols = SymbolSelector().select(session, prioritize_stale=True)

    assert symbols == ["2222", "1111"]


def test_prioritize_stale_combined_with_limit_bounds_the_batch(session):
    stock_a = _add_stock(session, "1111", with_bars=True)
    _add_stock(session, "2222", with_bars=True)  # never scanned
    _add_stock(session, "3333", with_bars=True)  # never scanned

    _record_evaluation(session, stock_a, datetime.now(timezone.utc))

    symbols = SymbolSelector().select(session, limit=2, prioritize_stale=True)

    assert len(symbols) == 2
    assert "1111" not in symbols  # the only already-evaluated symbol is deprioritized out of a 2-slot batch
