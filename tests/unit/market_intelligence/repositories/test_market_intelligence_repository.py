"""Repository tests for MarketIntelligenceRepository -- real SQLAlchemy
ORM against an in-memory SQLite DB, no mocking of the persistence
layer itself.
"""

from datetime import datetime, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.recommendation.types import AnalysisContext, Recommendation
from src.core.db.database import Base
from src.domain.models import (
    AlertSeverity,
    AlertType,
    CalibrationConfig,
    CalibrationStatus,
    MarketScanRun,
    MarketScanStatus,
    RecommendationLabel,
    RecommendationSnapshot,
    Stock,
)
from src.market_intelligence.repositories import market_intelligence_repository as repository_module
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def repo():
    return MarketIntelligenceRepository()


def test_create_scan_run_starts_pending(session, repo):
    run = repo.create_scan_run(session, symbols_requested=5)
    assert run.status is MarketScanStatus.PENDING
    assert run.symbols_requested == 5
    assert run.id is not None


def test_mark_running_and_finish_run_lifecycle(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id

    started_at = repo.mark_running(session, run_id)
    assert started_at.tzinfo is not None

    repo.finish_run(
        session, run_id, MarketScanStatus.SUCCESS,
        symbols_succeeded=1, symbols_skipped=0, symbols_failed=0, started_at=started_at,
    )

    reloaded = repo.get_run(session, run_id)
    assert reloaded.status is MarketScanStatus.SUCCESS
    assert reloaded.symbols_succeeded == 1
    assert reloaded.duration_seconds is not None


def test_finish_run_without_started_at_leaves_duration_none(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, run.id, MarketScanStatus.FAILED, symbols_succeeded=0, symbols_skipped=0, symbols_failed=1)
    reloaded = repo.get_run(session, run.id)
    assert reloaded.duration_seconds is None
    assert reloaded.status is MarketScanStatus.FAILED


def test_get_run_returns_none_for_unknown_id(session, repo):
    assert repo.get_run(session, 9999) is None


def test_reap_stale_runs_marks_old_pending_and_running_runs_failed(session, repo):
    from datetime import timedelta

    stale_pending = repo.create_scan_run(session, symbols_requested=1)
    stale_running = repo.create_scan_run(session, symbols_requested=1)
    repo.mark_running(session, stale_running.id)
    fresh_running = repo.create_scan_run(session, symbols_requested=1)
    repo.mark_running(session, fresh_running.id)

    # Backdate the two "stale" runs' created_at directly (bypassing the
    # model's own default) to simulate a run that crashed hours ago.
    old = datetime.now(timezone.utc) - timedelta(hours=10)
    session.query(MarketScanRun).filter(
        MarketScanRun.id.in_([stale_pending.id, stale_running.id])
    ).update({"created_at": old}, synchronize_session=False)
    session.commit()

    reaped = repo.reap_stale_runs(session, max_age_hours=4)

    reaped_ids = {run.id for run in reaped}
    assert reaped_ids == {stale_pending.id, stale_running.id}
    assert repo.get_run(session, stale_pending.id).status is MarketScanStatus.FAILED
    assert repo.get_run(session, stale_running.id).status is MarketScanStatus.FAILED
    assert repo.get_run(session, fresh_running.id).status is MarketScanStatus.RUNNING


def test_reap_stale_runs_leaves_recent_runs_untouched(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    reaped = repo.reap_stale_runs(session, max_age_hours=4)
    assert reaped == []
    assert repo.get_run(session, run.id).status is MarketScanStatus.PENDING


def test_get_latest_successful_run_ignores_failed_runs(session, repo):
    failed = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, failed.id, MarketScanStatus.FAILED, symbols_succeeded=0, symbols_skipped=0, symbols_failed=1)

    success = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, success.id, MarketScanStatus.SUCCESS, symbols_succeeded=1, symbols_skipped=0, symbols_failed=0)

    latest = repo.get_latest_successful_run(session)
    assert latest.id == success.id


def test_get_latest_successful_run_before_run_id(session, repo):
    run1 = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, run1.id, MarketScanStatus.SUCCESS, symbols_succeeded=1, symbols_skipped=0, symbols_failed=0)
    run2 = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, run2.id, MarketScanStatus.SUCCESS, symbols_succeeded=1, symbols_skipped=0, symbols_failed=0)

    previous = repo.get_latest_successful_run(session, before_run_id=run2.id)
    assert previous.id == run1.id


def _seed_stock(session, symbol="2222"):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


@pytest.mark.asyncio
async def test_save_and_read_back_symbol_records(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", decision=make_decision(symbol="2222", recommendation=Recommendation.BUY))

    await repo.save_symbol_records(session, run.id, [outcome])

    records = repo.get_symbol_records_by_symbol(session, run.id)
    assert "2222" in records
    assert records["2222"].recommendation is RecommendationLabel.BUY
    assert float(records["2222"].confidence) == outcome.confidence


@pytest.mark.asyncio
async def test_save_symbol_records_coerces_numpy_floats_before_they_reach_the_orm(session, repo, monkeypatch):
    """Regression test: technical/fundamental indicator computations
    return `numpy.float64` in places (confirmed via a live run against
    real Postgres -- SQLAlchemy 2.0's insertmanyvalues path literal-
    renders RETURNING parameters, and numpy's `repr()`
    (`np.float64(1.23)`) is not valid SQL, breaking every multi-row
    scan-result insert). SQLite (every other test here) tolerates the
    numpy type silently, and reading a Numeric column back always
    yields `Decimal` regardless of what was written -- so neither the
    value nor a post-commit read-back can distinguish a fixed call
    from a broken one. This test instead captures the exact object
    `session.add()` receives (via a spy) and checks *its* attribute
    types, which is what actually reaches the SQL layer."""
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    decision = make_decision(
        symbol="2222", confidence=np.float64(75.1), final_score=np.float64(61.8),
        target_price=np.float64(153.68), stop_loss=np.float64(148.91), expected_return_pct=np.float64(1.97),
    )
    outcome = make_outcome(
        symbol="2222", decision=decision, latest_price=np.float64(150.71),
        technical_snapshot={"rsi_14": np.float64(100.0), "adx_14": np.float64(100.0), "bollinger": {"upper": np.float64(32.889)}},
        fundamental_snapshot={"dividend_yield": np.float64(0.0023)},
    )

    fields = (
        "confidence", "final_score", "target_price", "stop_loss", "expected_return_pct",
        "latest_price", "rsi", "adx", "bollinger_upper", "dividend_yield",
    )
    snapshot_fields = (
        "total_score", "confidence_score", "target_price", "stop_loss",
        "expected_return_pct", "market_price_at_evaluation",
    )
    snapshots = []
    recommendation_snapshots = []
    original_add = session.add

    def _spy_add(obj):
        # Snapshot the attribute types *before* `session.commit()` (called
        # internally by save_symbol_records) expires the instance and any
        # later access silently re-queries the DB, which always returns
        # `Decimal` for a Numeric column regardless of what was written --
        # that would hide the exact bug this test exists to catch.
        if type(obj).__name__ == "SymbolIntelligenceRecord":
            snapshots.append({f: type(getattr(obj, f)) for f in fields})
        elif type(obj).__name__ == "RecommendationSnapshot":
            recommendation_snapshots.append({f: type(getattr(obj, f)) for f in snapshot_fields})
        return original_add(obj)

    monkeypatch.setattr(session, "add", _spy_add)

    await repo.save_symbol_records(session, run.id, [outcome])

    assert len(recommendation_snapshots) == 1
    for field, field_type in recommendation_snapshots[0].items():
        assert field_type is float, f"RecommendationSnapshot.{field} was {field_type!r}, expected plain float"

    assert len(snapshots) == 1
    for field, field_type in snapshots[0].items():
        assert field_type is float, f"{field} was {field_type!r} at insert time, expected plain float"


@pytest.mark.asyncio
async def test_save_symbol_records_also_writes_a_live_recommendation_snapshot(session, repo):
    """E1 of the AI Evolution Layer: every successful live scan outcome
    must also produce a RecommendationSnapshot row (run_id=None,
    source="live_scan") so accuracy tracking has real live data to
    evaluate later, not just backtest data."""
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    decision = make_decision(symbol="2222", recommendation=Recommendation.BUY, confidence=72.0, final_score=68.0)
    outcome = make_outcome(symbol="2222", decision=decision, latest_price=101.5)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").all()
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.run_id is None
    assert snapshot.source == "live_scan"
    assert snapshot.is_paper_trade is False
    assert snapshot.variant is None
    assert snapshot.recommendation is RecommendationLabel.BUY
    assert float(snapshot.confidence_score) == 72.0
    assert float(snapshot.total_score) == 68.0
    assert float(snapshot.market_price_at_evaluation) == 101.5
    assert snapshot.engine_version == "1.0.0"
    assert snapshot.contributor_breakdown == [
        {"category": "Technical Analysis", "points": 15.0, "weight": 0.25, "confidence": 90.0, "available": True, "notes": None}
    ]
    assert snapshot.signals == []
    assert snapshot.reasons == ["BUY on 2222."]


@pytest.mark.asyncio
async def test_save_symbol_records_snapshot_skips_failed_and_unregistered_outcomes(session, repo):
    run = repo.create_scan_run(session, symbols_requested=2)
    failed = make_outcome(symbol="2222", success=False, report=None, skipped_reason="insufficient_data")
    unregistered = make_outcome(symbol="9999")  # no matching Stock row seeded

    await repo.save_symbol_records(session, run.id, [failed, unregistered])

    assert session.query(RecommendationSnapshot).count() == 0


@pytest.mark.asyncio
async def test_save_symbol_records_skips_unregistered_stock(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="9999")  # no matching Stock row seeded

    await repo.save_symbol_records(session, run.id, [outcome])

    assert repo.get_symbol_records_by_symbol(session, run.id) == {}


@pytest.mark.asyncio
async def test_save_symbol_records_skips_failed_outcomes(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", success=False, report=None, skipped_reason="insufficient_data")

    await repo.save_symbol_records(session, run.id, [outcome])

    assert repo.get_symbol_records_by_symbol(session, run.id) == {}


@pytest.mark.asyncio
async def test_save_symbol_records_does_not_paper_trade_when_disabled(session, repo, monkeypatch):
    """E8: PAPER_TRADING_ENABLED defaults off -- a scan must write only
    the champion snapshot, unchanged from before E8 existed, even when
    a VALIDATED calibration candidate exists."""
    monkeypatch.setattr(repository_module, "is_paper_trading_enabled", lambda: False)
    _seed_stock(session, "2222")
    session.add(CalibrationConfig(version="v1", status=CalibrationStatus.VALIDATED, config={}))
    session.commit()
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", context=AnalysisContext(symbol="2222"))

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").all()
    assert len(snapshots) == 1
    assert snapshots[0].variant is None


@pytest.mark.asyncio
async def test_save_symbol_records_paper_trades_a_challenger_when_enabled(session, repo, monkeypatch):
    """E8: when PAPER_TRADING_ENABLED and a VALIDATED calibration
    candidate exists, a second challenger RecommendationSnapshot is
    written alongside the champion, scored off the exact same
    AnalysisContext the champion decision was built from."""
    monkeypatch.setattr(repository_module, "is_paper_trading_enabled", lambda: True)
    _seed_stock(session, "2222")
    session.add(CalibrationConfig(version="v1", status=CalibrationStatus.VALIDATED, config={}))
    session.commit()
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", context=AnalysisContext(symbol="2222"))

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").order_by(RecommendationSnapshot.id).all()
    assert len(snapshots) == 2
    champion, challenger = snapshots
    assert champion.variant == "champion"
    assert champion.is_paper_trade is False
    assert challenger.variant == "challenger"
    assert challenger.is_paper_trade is True
    assert challenger.calibration_version == "v1"


@pytest.mark.asyncio
async def test_save_symbol_records_paper_trading_enabled_but_no_context_skips_challenger(session, repo, monkeypatch):
    """A scan outcome with no `context` (e.g. an older code path, or a
    fixture that never populated one) simply gets no challenger --
    never an error."""
    monkeypatch.setattr(repository_module, "is_paper_trading_enabled", lambda: True)
    _seed_stock(session, "2222")
    session.add(CalibrationConfig(version="v1", status=CalibrationStatus.VALIDATED, config={}))
    session.commit()
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", context=None)

    await repo.save_symbol_records(session, run.id, [outcome])

    assert session.query(RecommendationSnapshot).filter_by(symbol="2222").count() == 1


@pytest.mark.asyncio
async def test_save_symbol_records_paper_trading_enabled_but_no_validated_config_skips_challenger(session, repo, monkeypatch):
    monkeypatch.setattr(repository_module, "is_paper_trading_enabled", lambda: True)
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", context=AnalysisContext(symbol="2222"))

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").all()
    assert len(snapshots) == 1
    assert snapshots[0].variant is None


def test_save_and_read_back_sector_summaries(session, repo):
    from src.market_intelligence.types import SectorSummary

    run = repo.create_scan_run(session, symbols_requested=1)
    summary = SectorSummary(
        sector="Energy", symbol_count=2, average_confidence=70.0, average_final_score=65.0,
        average_expected_return_pct=5.0, average_technical_score=60.0, average_fundamental_score=55.0,
        buy_count=1, sell_count=0, hold_count=1, breadth=0.5, momentum=None,
    )
    repo.save_sector_summaries(session, run.id, [summary])

    rows = repo.get_sector_summaries(session, run.id)
    assert len(rows) == 1
    assert rows[0].sector == "Energy"

    scores = repo.get_sector_average_scores(session, run.id)
    assert scores == {"Energy": 65.0}


def test_save_and_read_back_alerts_with_filters(session, repo):
    from src.market_intelligence.types import Alert, AlertSeverity as TypesAlertSeverity, AlertType as TypesAlertType

    run = repo.create_scan_run(session, symbols_requested=1)
    now = datetime.now(timezone.utc)
    alerts = [
        Alert(alert_type=TypesAlertType.NEW_STRONG_BUY, severity=TypesAlertSeverity.INFO, symbol="A", sector=None, message="m1", generated_at=now),
        Alert(alert_type=TypesAlertType.RISK_SPIKE, severity=TypesAlertSeverity.CRITICAL, symbol="B", sector=None, message="m2", generated_at=now),
    ]
    repo.save_alerts(session, run.id, alerts)

    total, rows = repo.get_alerts(session, limit=50, offset=0)
    assert total == 2

    total, rows = repo.get_alerts(session, limit=50, offset=0, severity=AlertSeverity.CRITICAL.value)
    assert total == 1
    assert rows[0].symbol == "B"

    total, rows = repo.get_alerts(session, limit=50, offset=0, alert_type=AlertType.NEW_STRONG_BUY.value)
    assert total == 1
    assert rows[0].symbol == "A"


def test_save_and_read_back_change_events_with_pagination(session, repo):
    from src.market_intelligence.types import ChangeEvent, ChangeType as TypesChangeType

    run = repo.create_scan_run(session, symbols_requested=1)
    now = datetime.now(timezone.utc)
    events = [
        ChangeEvent(symbol=f"S{i}", change_type=TypesChangeType.SCORE_CHANGE, previous_value="40", new_value="50", delta=10.0, detected_at=now)
        for i in range(5)
    ]
    repo.save_change_events(session, run.id, events)

    total, rows = repo.get_change_events(session, limit=2, offset=0, run_id=run.id)
    assert total == 5
    assert len(rows) == 2

    total, rows = repo.get_change_events(session, limit=50, offset=0, run_id=9999)
    assert total == 0


@pytest.mark.asyncio
async def test_get_market_breadth_aggregates_real_symbol_records(session, repo):
    """Phase 2C: a single aggregate query, not a per-row Python loop --
    seeds a mix of BUY/STRONG_BUY/SELL/HOLD outcomes and checks the
    counts/average confidence match what was actually saved."""
    for symbol in ["1010", "1020", "1030", "1040"]:
        _seed_stock(session, symbol)
    run = repo.create_scan_run(session, symbols_requested=4)
    outcomes = [
        make_outcome(symbol="1010", decision=make_decision(symbol="1010", recommendation=Recommendation.BUY, confidence=80.0)),
        make_outcome(symbol="1020", decision=make_decision(symbol="1020", recommendation=Recommendation.STRONG_BUY, confidence=90.0)),
        make_outcome(symbol="1030", decision=make_decision(symbol="1030", recommendation=Recommendation.SELL, confidence=60.0)),
        make_outcome(symbol="1040", decision=make_decision(symbol="1040", recommendation=Recommendation.HOLD, confidence=50.0)),
    ]
    await repo.save_symbol_records(session, run.id, outcomes)

    breadth = repo.get_market_breadth(session, run.id)

    assert breadth is not None
    assert breadth.scan_run_id == run.id
    assert breadth.symbols_scanned == 4
    assert breadth.buy_count == 2  # BUY + STRONG_BUY
    assert breadth.sell_count == 1
    assert breadth.average_confidence == pytest.approx(70.0)


def test_get_market_breadth_returns_none_for_a_run_with_no_records(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    assert repo.get_market_breadth(session, run.id) is None


def test_get_market_breadth_returns_none_for_an_unknown_run_id(session, repo):
    assert repo.get_market_breadth(session, 9999) is None
