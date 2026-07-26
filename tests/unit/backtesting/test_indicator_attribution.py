"""Unit tests for src.backtesting.calibration.indicator_attribution --
full DB integration against an in-memory SQLite DB, the same pattern
test_engine.py already uses for BacktestingEngine itself."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backtesting.calibration.indicator_attribution import (
    _forward_return_pct,
    _risk_bucket,
    _volatility_bucket_report,
    run_indicator_attribution,
)
from src.backtesting.calibration.indicator_signals import DIRECTIONAL_INDICATORS, RISK_INDICATORS
from src.core.db.database import Base
from src.domain.models import DataProvenanceMode, PriceBar, Stock, Timeframe

import pandas as pd


# --- pure helpers ------------------------------------------------------


def test_forward_return_pct_basic():
    df = pd.DataFrame({"close": [100.0, 110.0]})
    assert _forward_return_pct(100.0, df) == pytest.approx(10.0)


def test_forward_return_pct_none_when_no_future_data():
    assert _forward_return_pct(100.0, pd.DataFrame()) is None
    assert _forward_return_pct(None, pd.DataFrame({"close": [100.0]})) is None


def test_risk_bucket_atr_thresholds():
    assert _risk_bucket("atr", 0.01) == "low"
    assert _risk_bucket("atr", 0.02) == "moderate"
    assert _risk_bucket("atr", 0.05) == "high"


def test_risk_bucket_bollinger_thresholds():
    assert _risk_bucket("bollinger", 0.02) == "low"
    assert _risk_bucket("bollinger", 0.06) == "moderate"
    assert _risk_bucket("bollinger", 0.15) == "high"


def test_volatility_bucket_report_skips_empty_buckets():
    report = _volatility_bucket_report({"low": [1.0, 2.0], "moderate": [], "high": []})
    assert set(report.keys()) == {"low"}
    assert report["low"]["sample_size"] == 2


def test_volatility_bucket_report_none_realized_volatility_with_one_sample():
    report = _volatility_bucket_report({"low": [1.0]})
    assert report["low"]["realized_volatility"] is None


# --- full DB integration -------------------------------------------------


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _seed_stock_with_oscillating_bars(session, symbol="2222", count=200, source="dev-synthetic", is_synthetic=True):
    """A gently oscillating-but-net-upward series (unlike a pure
    monotonic ramp) so RSI/MACD/EMA-vs-SMA/ADX/swing-pivot detection
    all have real up-and-down movement to read, closer to genuine
    market data than a straight line."""
    import math

    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        price = 30.0 + i * 0.05 + math.sin(i / 5.0) * 1.5
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(round(price, 4))), high=Decimal(str(round(price + 0.3, 4))),
                low=Decimal(str(round(price - 0.3, 4))), close=Decimal(str(round(price, 4))),
                volume=1000 + i * 3, source=source, is_synthetic=is_synthetic,
            )
        )
    session.commit()
    return stock


def test_run_indicator_attribution_covers_every_indicator(session):
    _seed_stock_with_oscillating_bars(session)
    report = run_indicator_attribution(
        session, symbols=["2222"], start_date=date(2026, 3, 1), end_date=date(2026, 6, 1),
        data_provenance_mode=DataProvenanceMode.SYNTHETIC, evaluation_frequency_days=7, holding_horizon_days=20,
    )
    assert report.evaluated_count > 0
    assert set(report.directional_indicators.keys()) == set(DIRECTIONAL_INDICATORS)
    assert set(report.risk_indicators.keys()) == set(RISK_INDICATORS)


def test_directional_indicator_report_has_full_metrics_shape(session):
    _seed_stock_with_oscillating_bars(session)
    report = run_indicator_attribution(
        session, symbols=["2222"], start_date=date(2026, 3, 1), end_date=date(2026, 6, 1),
        data_provenance_mode=DataProvenanceMode.SYNTHETIC, evaluation_frequency_days=7, holding_horizon_days=20,
    )
    rsi_report = report.directional_indicators["rsi"]
    assert "win_rate" in rsi_report
    assert "precision_recall" in rsi_report
    assert "calibration_error" in rsi_report
    assert "sharpe_ratio" in rsi_report
    assert rsi_report["evaluation_count"] > 0


def test_risk_indicator_report_has_bucketed_volatility_shape(session):
    _seed_stock_with_oscillating_bars(session)
    report = run_indicator_attribution(
        session, symbols=["2222"], start_date=date(2026, 3, 1), end_date=date(2026, 6, 1),
        data_provenance_mode=DataProvenanceMode.SYNTHETIC, evaluation_frequency_days=7, holding_horizon_days=20,
    )
    atr_report = report.risk_indicators["atr"]
    assert atr_report  # at least one bucket populated
    for bucket in atr_report.values():
        assert "sample_size" in bucket
        assert "average_forward_return_pct" in bucket


def test_unknown_symbol_is_skipped_not_an_error(session):
    _seed_stock_with_oscillating_bars(session, symbol="2222")
    report = run_indicator_attribution(
        session, symbols=["9999"], start_date=date(2026, 3, 1), end_date=date(2026, 4, 1),
        data_provenance_mode=DataProvenanceMode.SYNTHETIC,
    )
    assert report.evaluated_count == 0
    assert report.skipped["symbol_not_found"] > 0


def test_provenance_mismatch_is_skipped_not_blended(session):
    _seed_stock_with_oscillating_bars(session, symbol="2222", is_synthetic=True)
    report = run_indicator_attribution(
        session, symbols=["2222"], start_date=date(2026, 3, 1), end_date=date(2026, 4, 1),
        data_provenance_mode=DataProvenanceMode.LIVE,  # declared LIVE but bars are synthetic
    )
    assert report.evaluated_count == 0
    assert report.skipped["provenance_mismatch"] > 0
