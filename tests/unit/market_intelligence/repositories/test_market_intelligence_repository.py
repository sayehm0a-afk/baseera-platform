"""Repository tests for MarketIntelligenceRepository -- real SQLAlchemy
ORM against an in-memory SQLite DB, no mocking of the persistence
layer itself.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.recommendation.types import Recommendation
from src.core.db.database import Base
from src.domain.models import AlertSeverity, AlertType, MarketScanStatus, RecommendationLabel, Stock
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


def test_save_and_read_back_symbol_records(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", decision=make_decision(symbol="2222", recommendation=Recommendation.BUY))

    repo.save_symbol_records(session, run.id, [outcome])

    records = repo.get_symbol_records_by_symbol(session, run.id)
    assert "2222" in records
    assert records["2222"].recommendation is RecommendationLabel.BUY
    assert float(records["2222"].confidence) == outcome.confidence


def test_save_symbol_records_skips_unregistered_stock(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="9999")  # no matching Stock row seeded

    repo.save_symbol_records(session, run.id, [outcome])

    assert repo.get_symbol_records_by_symbol(session, run.id) == {}


def test_save_symbol_records_skips_failed_outcomes(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", success=False, report=None, skipped_reason="insufficient_data")

    repo.save_symbol_records(session, run.id, [outcome])

    assert repo.get_symbol_records_by_symbol(session, run.id) == {}


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
