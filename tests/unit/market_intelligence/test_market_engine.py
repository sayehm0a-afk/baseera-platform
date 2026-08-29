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


class _CapturingFakeScanner(_FakeScanner):
    """Same as `_FakeScanner`, but records the `market_breadth` it was
    actually called with -- the Decision V2 input `execute_scan`
    resolves at line ~103, and the Market Engine Shadow contamination
    fix's entire point is what this captures."""

    _UNSET = object()

    def __init__(self, outcomes):
        super().__init__(outcomes)
        self.received_market_breadth = self._UNSET

    async def scan(self, symbols, on_symbol_start=None, on_symbol_complete=None, on_retry=None, market_breadth=None):
        self.received_market_breadth = market_breadth
        return await super().scan(symbols, on_symbol_start, on_symbol_complete, on_retry, market_breadth)


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


# --- Market Engine Shadow contamination fix -----------------------------
#
# Independent-audit-mandated closure (Basirah mandate: "URGENT MARKET
# ENGINE CONTAMINATION AUDIT + FIX"): execute_scan's own two internal
# "latest/previous run" resolutions (market breadth for this run's own
# Decision V2 pass, and the previous run for sector momentum / change
# detection) used the unfiltered get_latest_successful_run -- unlike
# every consumer-facing route, which PR #105 already routed through
# get_latest_consumer_visible_run. A Shadow-internal run could
# therefore silently become the market_breadth fed into this run's OWN
# real Decision V2 computation (classify_market_risk -> confidence cap
# / entry-gate), or the "previous run" this run's sector momentum is
# computed against -- contaminating real output, not just a consumer
# read. These tests use a 15-symbol Shadow run (the actual
# classify_market_risk minimum, _MINIMUM_SYMBOLS_FOR_CLASSIFICATION),
# not today's incidental 3-symbol Shadow cap, so the proof holds for
# any future Shadow configuration, not just the current one.

_SHADOW_SYMBOLS = [f"9{i:03d}" for i in range(15)]


def _seed_stocks(factory, symbols, sector="Energy"):
    session = factory()
    for symbol in symbols:
        session.add(Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector))
    session.commit()
    session.close()


async def _run_shadow_scan(factory, repo, symbols=_SHADOW_SYMBOLS, recommendation=Recommendation.STRONG_BUY):
    """Mirrors RecurrentLiveScanScheduler._run_one_cycle exactly:
    create_scan_run(is_shadow_internal=True), then Stage 2 runs and
    finish_run() commits SUCCESS -- all before any RecurrentScanCycle
    row would be written in production. No RecurrentScanCycle row is
    created here at all, deliberately: this reproduces the race window
    itself (Shadow SUCCESS, no cycle association yet), not just the
    eventual settled state PR #105's own tests already cover."""
    outcomes = [
        make_outcome(symbol=s, decision=make_decision(symbol=s, recommendation=recommendation, final_score=90.0))
        for s in symbols
    ]
    shadow_engine = MarketIntelligenceEngine(
        factory, market_provider=object(), repository=repo,
        scanner=_FakeScanner(outcomes), symbol_selector=_FakeSymbolSelector(symbols),
    )
    session = factory()
    shadow_run = repo.create_scan_run(session, symbols_requested=len(symbols), is_shadow_internal=True)
    shadow_run_id = shadow_run.id
    session.close()
    await shadow_engine.execute_scan(shadow_run_id)
    return shadow_run_id


class TestMarketEngineNeverSelectsAShadowInternalRun:
    @pytest.mark.asyncio
    async def test_market_breadth_is_none_when_the_only_completed_run_is_shadow_internal(self, factory):
        """Direct reproduction of the contamination vector at the
        engine boundary: with only a completed 15-symbol Shadow run on
        record, a real run's Decision V2 pass must resolve
        market_breadth=None (INSUFFICIENT_DATA, honest), never the
        Shadow run's breadth."""
        _seed_stocks(factory, _SHADOW_SYMBOLS)
        _seed_stocks(factory, ["2222"])
        repo = MarketIntelligenceRepository()

        await _run_shadow_scan(factory, repo)

        capturing_scanner = _CapturingFakeScanner([make_outcome(symbol="2222", decision=make_decision(symbol="2222"))])
        real_engine = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=capturing_scanner, symbol_selector=_FakeSymbolSelector(["2222"]),
        )
        session = factory()
        real_run = repo.create_scan_run(session, symbols_requested=1)
        real_run_id = real_run.id
        session.close()

        await real_engine.execute_scan(real_run_id)

        assert capturing_scanner.received_market_breadth is None

    @pytest.mark.asyncio
    async def test_market_breadth_from_a_real_previous_run_still_flows_through(self, factory):
        """Non-regression: the fix must not over-exclude -- a REAL
        completed prior run's breadth must still reach the next run's
        Decision V2 pass exactly as before."""
        _seed_stocks(factory, ["1111"])
        _seed_stocks(factory, ["2222"])
        repo = MarketIntelligenceRepository()

        first_engine = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=_FakeScanner([make_outcome(symbol="1111", decision=make_decision(symbol="1111", recommendation=Recommendation.BUY))]),
            symbol_selector=_FakeSymbolSelector(["1111"]),
        )
        session = factory()
        first_run = repo.create_scan_run(session, symbols_requested=1)
        first_run_id = first_run.id
        session.close()
        await first_engine.execute_scan(first_run_id)

        capturing_scanner = _CapturingFakeScanner([make_outcome(symbol="2222", decision=make_decision(symbol="2222"))])
        second_engine = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=capturing_scanner, symbol_selector=_FakeSymbolSelector(["2222"]),
        )
        session = factory()
        second_run = repo.create_scan_run(session, symbols_requested=1)
        second_run_id = second_run.id
        session.close()
        await second_engine.execute_scan(second_run_id)

        assert capturing_scanner.received_market_breadth is not None
        assert capturing_scanner.received_market_breadth.scan_run_id == first_run_id
        assert capturing_scanner.received_market_breadth.symbols_scanned == 1

    @pytest.mark.asyncio
    async def test_market_breadth_prefers_a_real_run_over_a_more_recent_shadow_run(self, factory):
        """The Shadow run has a higher (more recent) id than the real
        one -- an id/recency-based resolution would pick it. The fix
        must still resolve the real, older run's breadth."""
        _seed_stocks(factory, ["1111"])
        _seed_stocks(factory, _SHADOW_SYMBOLS)
        _seed_stocks(factory, ["2222"])
        repo = MarketIntelligenceRepository()

        real_engine_1 = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=_FakeScanner([make_outcome(symbol="1111", decision=make_decision(symbol="1111"))]),
            symbol_selector=_FakeSymbolSelector(["1111"]),
        )
        session = factory()
        real_run_1 = repo.create_scan_run(session, symbols_requested=1)
        real_run_1_id = real_run_1.id
        session.close()
        await real_engine_1.execute_scan(real_run_1_id)

        await _run_shadow_scan(factory, repo)  # more recent id than real_run_1

        capturing_scanner = _CapturingFakeScanner([make_outcome(symbol="2222", decision=make_decision(symbol="2222"))])
        real_engine_2 = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=capturing_scanner, symbol_selector=_FakeSymbolSelector(["2222"]),
        )
        session = factory()
        real_run_2 = repo.create_scan_run(session, symbols_requested=1)
        real_run_2_id = real_run_2.id
        session.close()
        await real_engine_2.execute_scan(real_run_2_id)

        assert capturing_scanner.received_market_breadth is not None
        assert capturing_scanner.received_market_breadth.scan_run_id == real_run_1_id
        assert capturing_scanner.received_market_breadth.symbols_scanned == 1

    @pytest.mark.asyncio
    async def test_sector_momentum_is_computed_against_the_real_previous_run_not_a_shadow_run(self, factory):
        """The second traced contamination vector (execute_scan line
        ~137): previous_run also drives sector momentum and change
        detection. A Shadow run's sector score must never be used as
        the "previous" baseline, even when it is the most recent
        completed run."""
        _seed_stocks(factory, ["1111"], sector="Energy")
        _seed_stocks(factory, _SHADOW_SYMBOLS, sector="Energy")
        _seed_stocks(factory, ["2222"], sector="Energy")
        repo = MarketIntelligenceRepository()

        real_engine_1 = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=_FakeScanner([make_outcome(symbol="1111", sector="Energy", decision=make_decision(symbol="1111", final_score=50.0))]),
            symbol_selector=_FakeSymbolSelector(["1111"]),
        )
        session = factory()
        real_run_1 = repo.create_scan_run(session, symbols_requested=1)
        real_run_1_id = real_run_1.id
        session.close()
        await real_engine_1.execute_scan(real_run_1_id)

        # Shadow run: same sector, deliberately a very different score
        # (90.0) and more recent id -- if picked, momentum would be
        # 80.0 - 90.0 = -10.0 instead of the correct 80.0 - 50.0 = 30.0.
        await _run_shadow_scan(factory, repo)

        real_engine_2 = MarketIntelligenceEngine(
            factory, market_provider=object(), repository=repo,
            scanner=_FakeScanner([make_outcome(symbol="2222", sector="Energy", decision=make_decision(symbol="2222", final_score=80.0))]),
            symbol_selector=_FakeSymbolSelector(["2222"]),
        )
        session = factory()
        real_run_2 = repo.create_scan_run(session, symbols_requested=1)
        real_run_2_id = real_run_2.id
        session.close()
        await real_engine_2.execute_scan(real_run_2_id)

        session = factory()
        sectors = repo.get_sector_summaries(session, real_run_2_id)
        session.close()
        assert len(sectors) == 1
        assert sectors[0].sector == "Energy"
        assert float(sectors[0].momentum) == pytest.approx(30.0, abs=0.01)


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
