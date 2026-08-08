"""Unit tests for MarketIntelligenceEngine -- uses a fake MarketScanner
(hand-built outcomes, no real analysis pipeline) against a real, in-
memory-SQLite-backed MarketIntelligenceRepository, isolating engine
orchestration from a real scan (already covered by test_scanner.py)
and from a real ranking/watchlist/sector/change/alert run (each
already covered by their own test files).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.recommendation.types import Recommendation
from src.core.db.database import Base
from src.domain.models import MarketScanStatus, Stock
from src.market_data.strict_mode import StrictRealDataUnavailableError
from src.market_intelligence.market_engine import MarketIntelligenceEngine
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


def _seed_stock(factory, symbol, sector="Energy"):
    session = factory()
    session.add(Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector))
    session.commit()
    session.close()


class _FakeScanner:
    def __init__(self, outcomes):
        self._outcomes = outcomes

    async def scan(self, symbols, on_symbol_start=None, on_symbol_complete=None, on_retry=None, market_breadth=None):
        for outcome in self._outcomes:
            if on_symbol_start is not None:
                on_symbol_start(outcome.symbol)
            if on_symbol_complete is not None:
                on_symbol_complete(outcome)
        return self._outcomes


class _FakeSymbolSelector:
    def __init__(self, symbols):
        self._symbols = symbols

    def select(self, session, symbols=None):
        return symbols if symbols is not None else self._symbols


@pytest.mark.asyncio
async def test_execute_scan_persists_symbol_records_and_marks_success(factory):
    _seed_stock(factory, "2222")
    repo = MarketIntelligenceRepository()
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222"))]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    result = await engine.execute_scan(run_id)

    assert result == outcomes

    session = factory()
    run_row = repo.get_run(session, run_id)
    assert run_row.status is MarketScanStatus.SUCCESS
    assert run_row.symbols_succeeded == 1
    assert run_row.duration_seconds is not None

    records = repo.get_symbol_records_by_symbol(session, run_id)
    assert "2222" in records
    session.close()


@pytest.mark.asyncio
async def test_execute_scan_records_skipped_symbol_identities_and_reasons(factory):
    """Root-caused in production (run 98, 393 symbols, 2 skipped, no
    durable record of which or why): a skipped outcome must not be
    silently discarded once the scan succeeds -- symbols_skipped's
    aggregate count alone is not enough to root-cause a specific run."""
    _seed_stock(factory, "2222")
    _seed_stock(factory, "9999")
    repo = MarketIntelligenceRepository()
    outcomes = [
        make_outcome(symbol="2222", decision=make_decision(symbol="2222")),
        make_outcome(symbol="9999", success=False, report=None, skipped_reason="insufficient_data"),
    ]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222", "9999"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=2)
    run_id = run.id
    session.close()

    await engine.execute_scan(run_id)

    session = factory()
    run_row = repo.get_run(session, run_id)
    assert run_row.status is MarketScanStatus.SUCCESS
    assert run_row.symbols_skipped == 1
    assert run_row.skipped_symbols_summary == "9999: insufficient_data"
    session.close()


@pytest.mark.asyncio
async def test_execute_scan_leaves_skipped_symbols_summary_null_when_nothing_skipped(factory):
    _seed_stock(factory, "2222")
    repo = MarketIntelligenceRepository()
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222"))]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    await engine.execute_scan(run_id)

    session = factory()
    run_row = repo.get_run(session, run_id)
    assert run_row.skipped_symbols_summary is None
    session.close()


@pytest.mark.asyncio
async def test_execute_scan_persists_sector_summaries(factory):
    _seed_stock(factory, "2222", sector="Energy")
    repo = MarketIntelligenceRepository()
    outcomes = [make_outcome(symbol="2222", sector="Energy", decision=make_decision(symbol="2222", final_score=80.0))]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    await engine.execute_scan(run_id)

    session = factory()
    sectors = repo.get_sector_summaries(session, run_id)
    assert len(sectors) == 1
    assert sectors[0].sector == "Energy"
    session.close()


@pytest.mark.asyncio
async def test_second_scan_detects_changes_against_the_first(factory):
    _seed_stock(factory, "2222")
    repo = MarketIntelligenceRepository()

    session = factory()
    run1 = repo.create_scan_run(session, symbols_requested=1)
    run1_id = run1.id
    session.close()

    engine1 = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner([make_outcome(symbol="2222", decision=make_decision(symbol="2222", recommendation=Recommendation.HOLD))]),
        symbol_selector=_FakeSymbolSelector(["2222"]),
    )
    await engine1.execute_scan(run1_id)

    session = factory()
    run2 = repo.create_scan_run(session, symbols_requested=1)
    run2_id = run2.id
    session.close()

    engine2 = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner([make_outcome(symbol="2222", decision=make_decision(symbol="2222", recommendation=Recommendation.STRONG_BUY))]),
        symbol_selector=_FakeSymbolSelector(["2222"]),
    )
    await engine2.execute_scan(run2_id)

    session = factory()
    total, events = repo.get_change_events(session, limit=50, offset=0, run_id=run2_id)
    assert total >= 1
    assert any(e.previous_value == "HOLD" and e.new_value == "STRONG_BUY" for e in events)

    total_alerts, alerts = repo.get_alerts(session, limit=50, offset=0)
    assert any(a.alert_type.value == "NEW_STRONG_BUY" for a in alerts)
    session.close()


@pytest.mark.asyncio
async def test_execute_scan_marks_running_before_finishing(factory):
    _seed_stock(factory, "2222")
    repo = MarketIntelligenceRepository()
    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner([make_outcome(symbol="2222")]),
        symbol_selector=_FakeSymbolSelector(["2222"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    await engine.execute_scan(run_id)

    session = factory()
    run_row = repo.get_run(session, run_id)
    assert run_row.started_at is not None
    assert run_row.finished_at is not None
    assert run_row.started_at <= run_row.finished_at
    session.close()


# --- strict real-data mode: mixed real/synthetic batches must fail ----


@pytest.mark.asyncio
async def test_strict_mode_fails_the_whole_run_when_any_outcome_is_synthetic(factory, monkeypatch):
    """Defense in depth: provider_factory already refuses to hand out a
    synthetic provider under strict mode, so this should be
    structurally unreachable in normal operation -- but if any outcome
    is nonetheless marked synthetic, the entire run must fail and
    nothing from it may be persisted."""
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    _seed_stock(factory, "2222")
    _seed_stock(factory, "1120")
    repo = MarketIntelligenceRepository()
    outcomes = [
        make_outcome(symbol="2222", decision=make_decision(symbol="2222"), is_synthetic=False, data_source="SAHMK_REAL"),
        make_outcome(symbol="1120", decision=make_decision(symbol="1120"), is_synthetic=True, data_source="DEV_SYNTHETIC"),
    ]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222", "1120"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=2)
    run_id = run.id
    session.close()

    with pytest.raises(StrictRealDataUnavailableError, match="1120"):
        await engine.execute_scan(run_id)

    # Nothing from this run was persisted -- no symbol record for
    # either the real or the synthetic outcome.
    session = factory()
    assert repo.get_symbol_records_by_symbol(session, run_id) == {}
    session.close()


@pytest.mark.asyncio
async def test_strict_mode_failure_finalizes_the_run_instead_of_leaving_it_stuck_running(factory, monkeypatch):
    """Regression test: execute_scan() marks the run RUNNING before
    this check runs. Without a matching finalize-on-failure, the
    mixed-batch raise above left the MarketScanRun row stuck at
    RUNNING forever -- neither scan_job_runner nor the CI validation
    script re-enters this method to finish it. Found and fixed the
    same day this check was added."""
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    _seed_stock(factory, "2222")
    _seed_stock(factory, "1120")
    repo = MarketIntelligenceRepository()
    outcomes = [
        make_outcome(symbol="2222", decision=make_decision(symbol="2222"), is_synthetic=False, data_source="SAHMK_REAL"),
        make_outcome(symbol="1120", decision=make_decision(symbol="1120"), is_synthetic=True, data_source="DEV_SYNTHETIC"),
    ]
    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222", "1120"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=2)
    run_id = run.id
    session.close()

    with pytest.raises(StrictRealDataUnavailableError):
        await engine.execute_scan(run_id)

    session = factory()
    run_row = repo.get_run(session, run_id)
    assert run_row.status is MarketScanStatus.FAILED
    assert "1120" in run_row.error_summary
    assert run_row.finished_at is not None
    session.close()


@pytest.mark.asyncio
async def test_strict_mode_allows_an_all_real_batch(factory, monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    _seed_stock(factory, "2222")
    repo = MarketIntelligenceRepository()
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222"), is_synthetic=False, data_source="SAHMK_REAL")]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    result = await engine.execute_scan(run_id)
    assert result == outcomes


@pytest.mark.asyncio
async def test_non_strict_mode_does_not_check_data_source_at_all(factory):
    """Regression guard: outside strict mode, a synthetic outcome scans
    and persists exactly as it always has."""
    _seed_stock(factory, "2222")
    repo = MarketIntelligenceRepository()
    outcomes = [make_outcome(symbol="2222", decision=make_decision(symbol="2222"), is_synthetic=True, data_source="DEV_SYNTHETIC")]

    engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(["2222"]),
    )

    session = factory()
    run = repo.create_scan_run(session, symbols_requested=1)
    run_id = run.id
    session.close()

    result = await engine.execute_scan(run_id)
    assert result == outcomes
