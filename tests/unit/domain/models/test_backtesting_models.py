"""Unit tests for the Backtesting & Calibration Engine's domain models
-- BacktestRun, RecommendationSnapshot, CalibrationConfig -- plus the
new PriceBar.source/is_synthetic columns. Round-trip persistence, no
network.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    BacktestRun,
    BacktestRunStatus,
    CalibrationConfig,
    CalibrationStatus,
    DataProvenanceMode,
    PriceBar,
    RecommendationLabel,
    RecommendationSnapshot,
    Stock,
    Timeframe,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stock(session):
    s = Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy")
    session.add(s)
    session.commit()
    return s


# --- PriceBar.source/is_synthetic -----------------------------------------


def test_price_bar_requires_explicit_source_and_is_synthetic(session, stock):
    bar = PriceBar(
        stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=datetime.now(timezone.utc),
        open=Decimal("10"), high=Decimal("11"), low=Decimal("9"), close=Decimal("10.5"), volume=1000,
        source="dev-synthetic", is_synthetic=True,
    )
    session.add(bar)
    session.commit()
    fetched = session.query(PriceBar).one()
    assert fetched.source == "dev-synthetic"
    assert fetched.is_synthetic is True


def test_price_bar_source_defaults_conservatively_when_omitted(session, stock):
    """Simulates a row inserted through a path that doesn't set
    source/is_synthetic explicitly (e.g. raw SQL bypassing the ORM) --
    server_default must land on the conservative "assume synthetic"
    side, never silently claim verified-real provenance."""
    bar = PriceBar(
        stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=datetime.now(timezone.utc),
        open=Decimal("10"), high=Decimal("11"), low=Decimal("9"), close=Decimal("10.5"), volume=1000,
    )
    session.add(bar)
    session.commit()
    session.refresh(bar)
    assert bar.source == "unknown"
    assert bar.is_synthetic is True


# --- BacktestRun -----------------------------------------------------


def _make_run(**overrides):
    defaults = dict(
        idempotency_key="key-1",
        status=BacktestRunStatus.PENDING,
        symbols=["2222", "1120"],
        data_provenance_mode=DataProvenanceMode.SYNTHETIC,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
    )
    defaults.update(overrides)
    return BacktestRun(**defaults)


def test_backtest_run_defaults_on_insert(session):
    run = _make_run()
    session.add(run)
    session.commit()

    fetched = session.query(BacktestRun).one()
    assert fetched.status == BacktestRunStatus.PENDING
    assert fetched.strategy == "ai_decision_engine"
    assert fetched.evaluation_frequency_days == 7
    assert fetched.holding_horizon_days == 20
    assert fetched.target_price_horizon_days == 60
    assert float(fetched.transaction_cost_bps) == 0
    assert float(fetched.slippage_bps) == 0
    assert fetched.fundamental_reporting_lag_days == 45
    assert fetched.progress_current == 0
    assert fetched.cancel_requested is False
    assert fetched.symbols == ["2222", "1120"]


def test_backtest_run_idempotency_key_is_unique(session):
    session.add(_make_run(idempotency_key="dup"))
    session.commit()

    session.add(_make_run(idempotency_key="dup"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_backtest_run_progress_and_completion_update_in_place(session):
    run = _make_run()
    session.add(run)
    session.commit()
    run_id = run.id

    run.status = BacktestRunStatus.RUNNING
    run.progress_current = 3
    run.progress_total = 10
    session.commit()

    run.status = BacktestRunStatus.SUCCESS
    run.progress_current = 10
    run.finished_at = datetime.now(timezone.utc)
    run.duration_seconds = 42.5
    run.metrics = {"direction_accuracy": 0.55}
    session.commit()

    fetched = session.query(BacktestRun).filter_by(id=run_id).one()
    assert fetched.status == BacktestRunStatus.SUCCESS
    assert fetched.progress_current == 10
    assert float(fetched.duration_seconds) == 42.5
    assert fetched.metrics == {"direction_accuracy": 0.55}


# --- RecommendationSnapshot ------------------------------------------------


def _make_snapshot(stock, **overrides):
    defaults = dict(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        recommendation=RecommendationLabel.BUY,
        total_score=Decimal("65.0"),
        confidence_score=Decimal("70.0"),
        engine_version="1.0.0",
    )
    defaults.update(overrides)
    return RecommendationSnapshot(**defaults)


def test_recommendation_snapshot_round_trip(session, stock):
    snapshot = _make_snapshot(
        stock,
        technical_score=Decimal("60.0"),
        fundamental_score=Decimal("70.0"),
        target_price=Decimal("35.50"),
        stop_loss=Decimal("28.75"),
        time_horizon="MEDIUM_TERM",
        risk_level="MEDIUM",
        position_size="STANDARD",
        reasons=["Buy on 2222: final weighted score 65.0/100."],
        signals=[{"name": "rsi_14", "impact": 6.0}],
        contributor_breakdown=[{"category": "Technical Analysis", "points": 10.0}],
        price_bar_source="dev-synthetic",
        price_bar_is_synthetic=True,
    )
    session.add(snapshot)
    session.commit()

    fetched = session.query(RecommendationSnapshot).one()
    assert fetched.symbol == "2222"
    assert fetched.recommendation == RecommendationLabel.BUY
    assert float(fetched.total_score) == 65.0
    assert float(fetched.target_price) == 35.50
    assert fetched.reasons == ["Buy on 2222: final weighted score 65.0/100."]
    assert fetched.signals == [{"name": "rsi_14", "impact": 6.0}]
    assert fetched.price_bar_is_synthetic is True
    assert fetched.run_id is None  # a snapshot doesn't require a run


def test_recommendation_snapshot_unique_per_run_stock_evaluated_at(session, stock):
    run = _make_run()
    session.add(run)
    session.commit()

    session.add(_make_snapshot(stock, run_id=run.id))
    session.commit()

    session.add(_make_snapshot(stock, run_id=run.id))  # same run/stock/evaluated_at
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_recommendation_snapshot_same_stock_different_dates_allowed(session, stock):
    run = _make_run()
    session.add(run)
    session.commit()

    session.add(_make_snapshot(stock, run_id=run.id, evaluated_at=datetime(2026, 3, 1, tzinfo=timezone.utc)))
    session.add(_make_snapshot(stock, run_id=run.id, evaluated_at=datetime(2026, 3, 8, tzinfo=timezone.utc)))
    session.commit()
    assert session.query(RecommendationSnapshot).count() == 2


def test_run_snapshots_relationship_and_cascade_delete(session, stock):
    run = _make_run()
    session.add(run)
    session.commit()
    session.add(_make_snapshot(stock, run_id=run.id))
    session.commit()

    session.refresh(run)
    assert len(run.snapshots) == 1

    session.delete(run)
    session.commit()
    assert session.query(RecommendationSnapshot).count() == 0


# --- CalibrationConfig -------------------------------------------------


def test_calibration_config_round_trip(session):
    cfg = CalibrationConfig(
        version="cal-2026-001",
        status=CalibrationStatus.DRAFT,
        config={"contributor_weights": {"technical": 0.3, "fundamental": 0.3}},
        training_period_start=date(2026, 1, 1),
        training_period_end=date(2026, 3, 1),
        validation_period_start=date(2026, 3, 1),
        validation_period_end=date(2026, 4, 1),
        random_seed=42,
    )
    session.add(cfg)
    session.commit()

    fetched = session.query(CalibrationConfig).one()
    assert fetched.status == CalibrationStatus.DRAFT
    assert fetched.config["contributor_weights"]["technical"] == 0.3
    assert fetched.activated_at is None


def test_calibration_config_version_is_unique(session):
    session.add(CalibrationConfig(version="v1", status=CalibrationStatus.DRAFT, config={}))
    session.commit()

    session.add(CalibrationConfig(version="v1", status=CalibrationStatus.DRAFT, config={}))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_calibration_config_activation_lifecycle_fields(session):
    cfg = CalibrationConfig(version="v2", status=CalibrationStatus.VALIDATED, config={})
    session.add(cfg)
    session.commit()

    cfg.status = CalibrationStatus.ACTIVE
    cfg.activated_at = datetime.now(timezone.utc)
    session.commit()

    cfg.status = CalibrationStatus.ROLLED_BACK
    cfg.deactivated_at = datetime.now(timezone.utc)
    session.commit()

    fetched = session.query(CalibrationConfig).filter_by(version="v2").one()
    assert fetched.status == CalibrationStatus.ROLLED_BACK
    assert fetched.activated_at is not None
    assert fetched.deactivated_at is not None
