"""Unit tests for sector_strength.py -- Phase 3 area 4's activation of
the previously-dead sector-rotation input. Real SQLAlchemy ORM against
an in-memory SQLite DB, real PriceBar rows, no mocking of the query
layer -- the whole point of this module is a real DB-only computation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.decision_v2.sector_strength import LOOKBACK_DAYS, compute_sector_strength
from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _make_stock(session, symbol, sector="Energy"):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
    session.add(stock)
    session.commit()
    return stock


def _add_bars(session, stock, closes, start=None):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, close in enumerate(closes):
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=start + timedelta(days=i),
                open=Decimal(str(close)), high=Decimal(str(close)), low=Decimal(str(close)),
                close=Decimal(str(close)), volume=1000,
            )
        )
    session.commit()


def _df_from_closes(closes, start=None):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = [start + timedelta(days=i) for i in range(len(closes))]
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1000] * len(closes)},
        index=pd.DatetimeIndex(index),
    )


_TODAY = datetime.now(timezone.utc)
_FLAT = [100.0] * (LOOKBACK_DAYS + 1)


def test_unclassified_sector_is_not_computed(session):
    stock = _make_stock(session, "1111", sector=None)
    df = _df_from_closes(_FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    result = compute_sector_strength(session, stock, df)
    assert result.sector_strength_used is False
    assert result.sector_name is None
    assert result.stock_vs_sector_relative_strength is None


def test_insufficient_own_history_is_not_computed(session):
    stock = _make_stock(session, "1111", sector="Energy")
    df = _df_from_closes([100.0, 101.0])  # far fewer than LOOKBACK_DAYS + 1
    result = compute_sector_strength(session, stock, df)
    assert result.sector_strength_used is False
    assert result.sector_name == "Energy"
    assert result.stock_vs_sector_relative_strength is None


def test_too_few_peers_is_not_computed(session):
    stock = _make_stock(session, "1111", sector="Energy")
    # Only 2 peers, below MIN_PEER_COUNT=3.
    for symbol in ("2222", "3333"):
        peer = _make_stock(session, symbol, sector="Energy")
        _add_bars(session, peer, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    df = _df_from_closes(_FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    result = compute_sector_strength(session, stock, df)
    assert result.sector_strength_used is False


def test_stale_own_data_is_not_computed(session):
    stock = _make_stock(session, "1111", sector="Energy")
    for symbol in ("2222", "3333", "4444"):
        peer = _make_stock(session, symbol, sector="Energy")
        _add_bars(session, peer, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    # Own data's latest bar is 30 days old -- well past MAX_STALENESS_DAYS.
    df = _df_from_closes(_FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS + 30))
    result = compute_sector_strength(session, stock, df)
    assert result.sector_strength_used is False


def test_stale_peer_is_excluded_from_the_average_not_counted_as_zero(session):
    stock = _make_stock(session, "1111", sector="Energy")
    # Two fresh, real peers.
    for symbol in ("2222", "3333"):
        peer = _make_stock(session, symbol, sector="Energy")
        _add_bars(session, peer, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    # One stale peer, must not count -- if it silently counted as a
    # zero-return participant it would still leave 3 total peers, so
    # this test also proves the MIN_PEER_COUNT check applies to the
    # post-exclusion count, not the pre-exclusion candidate count.
    stale_peer = _make_stock(session, "4444", sector="Energy")
    _add_bars(session, stale_peer, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS + 30))

    df = _df_from_closes(_FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    result = compute_sector_strength(session, stock, df)
    assert result.sector_strength_used is False


def test_a_real_outperforming_stock_gets_positive_relative_strength(session):
    stock = _make_stock(session, "1111", sector="Energy")
    own_closes = [100.0 + i * 1.0 for i in range(LOOKBACK_DAYS + 1)]  # +21% over the window
    _add_bars(session, stock, own_closes, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    for symbol in ("2222", "3333", "4444"):
        peer = _make_stock(session, symbol, sector="Energy")
        _add_bars(session, peer, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))  # 0% return peers

    df = _df_from_closes(own_closes, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    result = compute_sector_strength(session, stock, df)

    assert result.sector_strength_used is True
    assert result.sector_name == "Energy"
    assert result.stock_vs_sector_relative_strength is not None
    assert result.stock_vs_sector_relative_strength > 0
    # Clamped to the contributor's expected [-1, 1] input range.
    assert -1.0 <= result.stock_vs_sector_relative_strength <= 1.0
    assert result.sector_strength_score is not None
    assert 0.0 <= result.sector_strength_score <= 100.0
    assert result.sector_data_timestamp is not None


def test_an_underperforming_stock_gets_negative_relative_strength(session):
    stock = _make_stock(session, "1111", sector="Energy")
    own_closes = [100.0 - i * 0.5 for i in range(LOOKBACK_DAYS + 1)]  # falling
    _add_bars(session, stock, own_closes, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    for symbol in ("2222", "3333", "4444"):
        peer = _make_stock(session, symbol, sector="Energy")
        peer_closes = [100.0 + i * 1.0 for i in range(LOOKBACK_DAYS + 1)]  # rising peers
        _add_bars(session, peer, peer_closes, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    df = _df_from_closes(own_closes, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    result = compute_sector_strength(session, stock, df)

    assert result.sector_strength_used is True
    assert result.stock_vs_sector_relative_strength is not None
    assert result.stock_vs_sector_relative_strength < 0


def test_peers_from_a_different_sector_are_never_included(session):
    stock = _make_stock(session, "1111", sector="Energy")
    _add_bars(session, stock, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    # Three real peers, but all in a different sector -- must not be
    # picked up as Energy peers.
    for symbol in ("2222", "3333", "4444"):
        peer = _make_stock(session, symbol, sector="Materials")
        _add_bars(session, peer, _FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))

    df = _df_from_closes(_FLAT, start=_TODAY - timedelta(days=LOOKBACK_DAYS))
    result = compute_sector_strength(session, stock, df)
    assert result.sector_strength_used is False
