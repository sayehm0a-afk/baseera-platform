"""Unit tests for ScanProgressTracker -- the live-progress publisher
built because GitHub Actions exposes no per-symbol progress for a
running job (confirmed: its logs API 404s until the job completes).
Uses a real, in-memory-SQLite-backed session_factory (matching every
other market_intelligence test's convention) so MarketScanProgress
persistence is exercised for real, not mocked.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import MarketScanProgress, MarketScanRun
from src.market_intelligence.scan_progress import ScanProgressTracker
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


def _seed_run(factory) -> int:
    session = factory()
    run = MarketScanRun()
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()
    return run_id


def _read_progress_row(factory, run_id: int) -> MarketScanProgress:
    session = factory()
    try:
        return session.query(MarketScanProgress).filter(MarketScanProgress.run_id == run_id).one()
    finally:
        session.close()


class TestRowCreationAndBasics:
    def test_creates_a_progress_row_at_construction(self, factory, tmp_path):
        run_id = _seed_run(factory)
        ScanProgressTracker(factory, run_id, eligible_discovered=5, output_dir=tmp_path)
        row = _read_progress_row(factory, run_id)
        assert row.status == "RUNNING"
        assert row.eligible_discovered == 5
        assert row.completed_count == 0

    def test_writes_live_progress_json_at_construction(self, factory, tmp_path):
        run_id = _seed_run(factory)
        ScanProgressTracker(factory, run_id, eligible_discovered=3, output_dir=tmp_path)
        path = tmp_path / "live_progress.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["eligible_discovered"] == 3
        assert data["completed_count"] == 0
        assert data["progress_pct"] == 0.0


class TestSymbolLifecycle:
    def test_on_symbol_start_sets_current_symbol_with_names(self, factory, tmp_path):
        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(
            factory, run_id, eligible_discovered=2, output_dir=tmp_path,
            symbol_names={"2222": {"name_en": "SAUDI ARAMCO", "name_ar": "أرامكو"}},
        )
        tracker.on_symbol_start("2222")
        row = _read_progress_row(factory, run_id)
        assert row.current_symbol == "2222"
        assert row.current_symbol_name_en == "SAUDI ARAMCO"
        assert row.current_symbol_name_ar == "أرامكو"

    def test_on_symbol_complete_success_increments_success_and_clears_current(self, factory, tmp_path):
        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=2, output_dir=tmp_path)
        tracker.on_symbol_start("2222")
        outcome = make_outcome(symbol="2222", decision=make_decision(symbol="2222"))
        tracker.on_symbol_complete(outcome)
        row = _read_progress_row(factory, run_id)
        assert row.completed_count == 1
        assert row.success_count == 1
        assert row.current_symbol is None
        assert row.last_completed_symbol == "2222"

    def test_on_symbol_complete_insufficient_data(self, factory, tmp_path):
        from src.market_intelligence.types import SymbolScanOutcome

        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=1, output_dir=tmp_path)
        outcome = SymbolScanOutcome(
            symbol="1263", sector=None, success=False, report=None, skipped_reason="insufficient_data"
        )
        tracker.on_symbol_complete(outcome)
        row = _read_progress_row(factory, run_id)
        assert row.insufficient_data_count == 1
        assert row.success_count == 0
        assert row.failed_count == 0

    def test_on_symbol_complete_real_error_counts_as_failed_and_records_latest_error(self, factory, tmp_path):
        from src.market_intelligence.types import SymbolScanOutcome

        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=1, output_dir=tmp_path)
        outcome = SymbolScanOutcome(symbol="9999", sector=None, success=False, report=None, error="boom")
        tracker.on_symbol_complete(outcome)
        row = _read_progress_row(factory, run_id)
        assert row.failed_count == 1
        assert "9999" in row.latest_error
        assert "boom" in row.latest_error

    def test_on_symbol_complete_generic_skip_without_reason_counts_as_skipped(self, factory, tmp_path):
        from src.market_intelligence.types import SymbolScanOutcome

        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=1, output_dir=tmp_path)
        outcome = SymbolScanOutcome(symbol="7777", sector=None, success=False, report=None)
        tracker.on_symbol_complete(outcome)
        row = _read_progress_row(factory, run_id)
        assert row.skipped_count == 1

    def test_accounting_invariant_holds_after_mixed_outcomes(self, factory, tmp_path):
        from src.market_intelligence.types import SymbolScanOutcome

        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=4, output_dir=tmp_path)
        tracker.on_symbol_complete(make_outcome(symbol="1", decision=make_decision(symbol="1")))
        tracker.on_symbol_complete(
            SymbolScanOutcome(symbol="2", sector=None, success=False, report=None, skipped_reason="insufficient_data")
        )
        tracker.on_symbol_complete(SymbolScanOutcome(symbol="3", sector=None, success=False, report=None, error="x"))
        tracker.on_symbol_complete(SymbolScanOutcome(symbol="4", sector=None, success=False, report=None))
        row = _read_progress_row(factory, run_id)
        assert row.completed_count == 4
        assert row.success_count + row.failed_count + row.skipped_count + row.insufficient_data_count == 4


class TestRetryAndFinalize:
    def test_on_retry_increments_retries_and_records_warning(self, factory, tmp_path):
        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=1, output_dir=tmp_path)
        tracker.on_retry("2222", 1, 3, ValueError("network blip"))
        row = _read_progress_row(factory, run_id)
        assert row.retries_total == 1
        assert "2222" in row.latest_warning

    def test_finalize_sets_status_and_completed_at(self, factory, tmp_path):
        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=1, output_dir=tmp_path)
        tracker.finalize("COMPLETED")
        row = _read_progress_row(factory, run_id)
        assert row.status == "COMPLETED"
        assert row.completed_at is not None


class TestNeverBreaksTheRealScan:
    def test_on_symbol_complete_swallows_internal_errors(self, factory, tmp_path):
        """A bug in progress tracking must never propagate into the
        real scan loop it's observing -- e.g. a None output_dir/broken
        filesystem must not raise out of on_symbol_complete."""
        run_id = _seed_run(factory)
        tracker = ScanProgressTracker(factory, run_id, eligible_discovered=1, output_dir=tmp_path)
        tracker._output_dir = None  # force _write_progress_file to fail internally
        outcome = make_outcome(symbol="2222", decision=make_decision(symbol="2222"))
        tracker.on_symbol_complete(outcome)  # must not raise
