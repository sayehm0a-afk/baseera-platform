"""Repository tests for MarketIntelligenceRepository -- real SQLAlchemy
ORM against an in-memory SQLite DB, no mocking of the persistence
layer itself.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.decision_v2.types import (
    DataFreshnessStatus, Decision, DecisionResult, GateOutcome, GateStatus, SubScores,
)
from src.analysis.recommendation.types import AnalysisContext, Recommendation
from src.core.db.database import Base
from src.domain.models import (
    AlertSeverity,
    AlertType,
    CalibrationConfig,
    CalibrationStatus,
    DecisionV2Snapshot,
    MarketScanRun,
    MarketScanStatus,
    RecommendationLabel,
    RecommendationSnapshot,
    RecurrentScanCycle,
    RecurrentScanCycleStatus,
    Stock,
)
from src.market_intelligence.repositories import market_intelligence_repository as repository_module
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def make_decision_v2_result(symbol="2222", **numpy_overrides) -> DecisionResult:
    """A minimal, real DecisionResult -- numeric fields default to
    numpy.float64 (matching what DecisionEngineV2.decide() actually
    produces from numpy-backed indicator computations) so tests can
    assert every one of them gets coerced before it reaches the ORM."""
    defaults = dict(
        confidence_score=np.float64(70.0),
        opportunity_quality_score=np.float64(60.5),
        risk_score=np.float64(40.0),
        data_quality_score=np.float64(100.0),
        current_price=np.float64(26.9),
        entry_zone_low=np.float64(26.5),
        entry_zone_high=np.float64(27.1),
        stop_loss=np.float64(26.46),
        target_1=np.float64(27.71),
        target_2=np.float64(28.3),
        target_3=np.float64(29.0),
        expected_return_target_1=np.float64(3.01),
        expected_return_target_2=np.float64(5.2),
        downside_to_stop=np.float64(1.6),
        risk_reward_target_1=np.float64(1.84),
        risk_reward_target_2=np.float64(2.1),
        technical_confidence=np.float64(50.0), momentum_confidence=np.float64(57.4),
        liquidity_confidence=np.float64(70.0), market_context_confidence=np.float64(75.0),
        data_quality_confidence=np.float64(100.0),
        best_entry_price=np.float64(26.6), accumulation_zone_low=np.float64(26.4),
        accumulation_zone_high=np.float64(26.9), invalidation_price=np.float64(26.3),
        nearest_support=np.float64(26.0), major_support=np.float64(25.0),
        nearest_resistance=np.float64(28.0), major_resistance=np.float64(29.5),
        breakout_level=np.float64(27.5), breakdown_level=np.float64(25.8),
        current_volume=np.float64(3_500_000.0), average_volume=np.float64(2_800_000.0),
        relative_volume=np.float64(1.25), accumulation_score=np.float64(65.0),
        market_breadth_average_confidence=np.float64(60.0),
    )
    defaults.update(numpy_overrides)
    return DecisionResult(
        symbol=symbol, company_name_ar="سهم", company_name_en=f"Stock {symbol}", sector_ar="الطاقة",
        decision=Decision.BUY_CANDIDATE, decision_label_ar="مرشح شراء",
        data_freshness_status=DataFreshnessStatus.LIVE,
        expected_holding_period_min_days=1, expected_holding_period_max_days=15,
        expected_holding_period_label_ar="من جلسة إلى 3 أسابيع", horizon_type="SHORT_TERM",
        market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        invalidation_conditions=[], positive_reasons=[], negative_reasons=[], warnings=[],
        recommendation_basis="test", analysis_version="2.0.0", data_source="SAHMK_REAL", scan_run_id=None,
        sub_scores=SubScores(
            trend_score=np.float64(50.0), momentum_score=np.float64(57.4), volume_score=np.float64(65.0),
            liquidity_score=np.float64(70.0), volatility_score=np.float64(30.0),
            risk_reward_score=np.float64(64.75), market_context_score=np.float64(75.0),
            data_quality_score=np.float64(100.0),
        ),
        gates=[GateOutcome(name="real_data_source", status=GateStatus.PASS, detail="ok", blocking=np.bool_(True))],
        **defaults,
    )


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


def _mark_shadow(session, run_id, cycle_id=None):
    import uuid

    row = RecurrentScanCycle(
        cycle_id=cycle_id or uuid.uuid4().hex,
        status=RecurrentScanCycleStatus.SUCCESS_NO_CHANGE,
        scan_run_id=run_id,
        triggered_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    return row


def _success_run(repo, session, symbols=1):
    run = repo.create_scan_run(session, symbols_requested=symbols)
    repo.finish_run(session, run.id, MarketScanStatus.SUCCESS, symbols_succeeded=symbols, symbols_skipped=0, symbols_failed=0)
    return repo.get_run(session, run.id)


class TestConsumerVisibleRunExcludesShadow:
    """Independent-audit-mandated closure of a real production
    consumer-isolation defect: /api/v1/market/* (and the sibling
    consumer surfaces in radar.py/stocks.py/rebalance_engine.py) could
    resolve a Shadow-internal MarketScanRun as "the latest scan"
    because get_latest_successful_run had no Shadow exclusion.
    RecurrentScanCycle.scan_run_id is written exclusively by
    recurrent_live_scan.py (no other module constructs that row), so it
    is a reliable, persisted, structural discriminator -- not a
    timestamp/ID heuristic."""

    def test_131_132_133_reproduction_latest_excludes_both_shadow_runs(self, session, repo):
        consumer_run = _success_run(repo, session)  # "131"
        shadow_1 = _success_run(repo, session)  # "132"
        _mark_shadow(session, shadow_1.id)
        shadow_2 = _success_run(repo, session)  # "133"
        _mark_shadow(session, shadow_2.id)

        latest = repo.get_latest_consumer_visible_run(session)
        assert latest is not None
        assert latest.id == consumer_run.id

    def test_131_132_133_reproduction_explicit_lookup_excludes_both_shadow_runs(self, session, repo):
        consumer_run = _success_run(repo, session)
        shadow_1 = _success_run(repo, session)
        _mark_shadow(session, shadow_1.id)
        shadow_2 = _success_run(repo, session)
        _mark_shadow(session, shadow_2.id)

        assert repo.get_consumer_visible_run(session, consumer_run.id).id == consumer_run.id
        assert repo.get_consumer_visible_run(session, shadow_1.id) is None
        assert repo.get_consumer_visible_run(session, shadow_2.id) is None

    def test_pre_fix_raw_helper_would_have_picked_the_shadow_run(self, session, repo):
        """Documents the exact defect this closes: the OLD, still-
        present (for staff/internal callers) get_latest_successful_run
        has no Shadow exclusion and really would pick the Shadow run --
        proving the new method's exclusion is the actual fix, not a
        pre-existing no-op."""
        consumer_run = _success_run(repo, session)
        shadow = _success_run(repo, session)
        _mark_shadow(session, shadow.id)

        assert repo.get_latest_successful_run(session).id == shadow.id
        assert repo.get_latest_consumer_visible_run(session).id == consumer_run.id

    @pytest.mark.parametrize("padding_run_count", [0, 200, 500, 999])
    def test_future_shadow_runs_with_arbitrary_ids_are_excluded(self, session, repo, padding_run_count):
        _success_run(repo, session)
        # Padding proves exclusion isn't an accidental "id > N"
        # heuristic -- it's purely relational (linked via
        # RecurrentScanCycle), never ID-based. A real 999-run pad is
        # too slow for a unit test, so this uses a small multiple
        # instead of the literal IDs 200/500/9999 -- the mechanism
        # under test (relational, not ID-based) is identical either way.
        for _ in range(min(padding_run_count, 5)):
            _success_run(repo, session)
        shadow = _success_run(repo, session)
        _mark_shadow(session, shadow.id)

        latest = repo.get_latest_consumer_visible_run(session)
        assert latest is not None
        assert latest.id != shadow.id
        assert repo.get_consumer_visible_run(session, shadow.id) is None

    def test_shadow_only_no_consumer_visible_scan_returns_none_not_shadow(self, session, repo):
        shadow = _success_run(repo, session)
        _mark_shadow(session, shadow.id)

        assert repo.get_latest_consumer_visible_run(session) is None

    def test_stale_normal_plus_fresh_shadow_still_picks_normal(self, session, repo):
        consumer_run = _success_run(repo, session)
        session.query(MarketScanRun).filter_by(id=consumer_run.id).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(days=3)}
        )
        session.commit()
        shadow = _success_run(repo, session)
        _mark_shadow(session, shadow.id)

        latest = repo.get_latest_consumer_visible_run(session)
        assert latest.id == consumer_run.id

    def test_failed_normal_plus_successful_shadow_returns_none_not_shadow(self, session, repo):
        run = repo.create_scan_run(session, symbols_requested=1)
        repo.finish_run(session, run.id, MarketScanStatus.FAILED, symbols_succeeded=0, symbols_skipped=0, symbols_failed=1)
        shadow = _success_run(repo, session)
        _mark_shadow(session, shadow.id)

        assert repo.get_latest_consumer_visible_run(session) is None

    def test_successful_normal_plus_failed_shadow_returns_normal(self, session, repo):
        consumer_run = _success_run(repo, session)
        shadow = repo.create_scan_run(session, symbols_requested=1)
        repo.finish_run(session, shadow.id, MarketScanStatus.FAILED, symbols_succeeded=0, symbols_skipped=0, symbols_failed=1)
        _mark_shadow(session, shadow.id)

        latest = repo.get_latest_consumer_visible_run(session)
        assert latest.id == consumer_run.id

    def test_no_scans_at_all_returns_none(self, session, repo):
        assert repo.get_latest_consumer_visible_run(session) is None
        assert repo.get_consumer_visible_run(session, 9999) is None

    def test_before_run_id_still_excludes_shadow(self, session, repo):
        run1 = _success_run(repo, session)
        shadow = _success_run(repo, session)
        _mark_shadow(session, shadow.id)
        run2 = _success_run(repo, session)

        previous = repo.get_latest_consumer_visible_run(session, before_run_id=run2.id)
        assert previous.id == run1.id

    def test_a_skipped_shadow_cycle_with_no_scan_run_id_does_not_affect_exclusion(self, session, repo):
        """A RecurrentScanCycle row with scan_run_id=None (a cycle
        skipped before Stage 2) must never accidentally exclude a real
        consumer run -- the exclusion subquery already filters out
        NULL scan_run_id values; this proves it end-to-end."""
        consumer_run = _success_run(repo, session)
        _mark_shadow(session, None)

        latest = repo.get_latest_consumer_visible_run(session)
        assert latest is not None
        assert latest.id == consumer_run.id


def test_record_stage1_metrics_persists_onto_the_run_row(session, repo):
    run = repo.create_scan_run(session, symbols_requested=15)
    repo.record_stage1_metrics(session, run.id, universe_size=231, candidate_count=52, evaluated_count=228)

    reloaded = repo.get_run(session, run.id)
    assert reloaded.stage1_universe_size == 231
    assert reloaded.stage1_evaluated_count == 228
    assert reloaded.stage1_candidate_count == 52


def test_record_stage1_metrics_on_an_unknown_run_id_is_a_harmless_no_op(session, repo):
    # A defensive guard, not an expected call pattern -- an UPDATE
    # against zero matching rows must never raise.
    repo.record_stage1_metrics(session, 999999, universe_size=100, candidate_count=10, evaluated_count=95)


def test_get_latest_run_with_stage1_metrics_is_none_when_no_radar_v2_cycle_has_completed(session, repo):
    ordinary_run = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, ordinary_run.id, MarketScanStatus.SUCCESS, symbols_succeeded=1, symbols_skipped=0, symbols_failed=0)
    assert repo.get_latest_run_with_stage1_metrics(session) is None


def test_get_latest_run_with_stage1_metrics_returns_the_most_recent_one(session, repo):
    older = repo.create_scan_run(session, symbols_requested=1)
    repo.record_stage1_metrics(session, older.id, universe_size=200, candidate_count=40, evaluated_count=198)

    newer = repo.create_scan_run(session, symbols_requested=1)
    repo.record_stage1_metrics(session, newer.id, universe_size=231, candidate_count=52, evaluated_count=228)

    latest = repo.get_latest_run_with_stage1_metrics(session)
    assert latest.id == newer.id
    assert latest.stage1_universe_size == 231
    assert latest.stage1_candidate_count == 52


def test_has_in_flight_run_returns_none_when_nothing_is_running(session, repo):
    assert repo.has_in_flight_run(session) is None


def test_has_in_flight_run_finds_a_pending_run(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    in_flight = repo.has_in_flight_run(session)
    assert in_flight is not None
    assert in_flight.id == run.id


def test_has_in_flight_run_finds_a_running_run(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    repo.mark_running(session, run.id)
    in_flight = repo.has_in_flight_run(session)
    assert in_flight is not None
    assert in_flight.id == run.id


def test_has_in_flight_run_ignores_finished_runs(session, repo):
    """The overlap guard's whole purpose: a completed/failed run must
    never block the next scan -- only PENDING/RUNNING count as
    'already in progress', the same distinction POST /market/scan and
    the admin diagnostic-scan route already relied on before this
    method centralized their identical inline query."""
    success = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, success.id, MarketScanStatus.SUCCESS, symbols_succeeded=1, symbols_skipped=0, symbols_failed=0)
    failed = repo.create_scan_run(session, symbols_requested=1)
    repo.finish_run(session, failed.id, MarketScanStatus.FAILED, symbols_succeeded=0, symbols_skipped=0, symbols_failed=1)

    assert repo.has_in_flight_run(session) is None


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
async def test_save_symbol_records_coerces_numpy_types_in_decision_v2_snapshot(session, repo):
    """Regression for a real production failure: the Phase 3A
    DecisionV2Snapshot write path (added alongside the V1 fix above)
    did not apply the same numpy coercion, so every scheduled scan run
    that reached this code failed with a real Postgres error
    (confirmed live: 'schema "np" does not exist' / 'Object of type
    bool is not JSON serializable') once DecisionEngineV2's numpy-
    backed indicator computations reached this batched insert. Uses
    the same session.add() spy technique as the V1 test above, since
    SQLite silently tolerates the un-coerced type and a post-commit
    read-back can't distinguish a fixed call from a broken one."""
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    decision_v2 = make_decision_v2_result(symbol="2222")
    outcome = make_outcome(symbol="2222", decision_v2=decision_v2)

    numeric_fields = (
        "confidence_score", "opportunity_quality_score", "risk_score", "data_quality_score",
        "current_price", "entry_zone_low", "entry_zone_high", "stop_loss",
        "target_1", "target_2", "target_3",
        "expected_return_target_1", "expected_return_target_2", "downside_to_stop",
        "risk_reward_target_1", "risk_reward_target_2",
        "technical_confidence", "momentum_confidence", "liquidity_confidence",
        "market_context_confidence", "data_quality_confidence",
        "best_entry_price", "accumulation_zone_low", "accumulation_zone_high", "invalidation_price",
        "nearest_support", "major_support", "nearest_resistance", "major_resistance",
        "breakout_level", "breakdown_level",
        "current_volume", "average_volume", "relative_volume", "accumulation_score",
        "market_breadth_average_confidence",
    )
    captured = []
    original_add = session.add

    def _spy_add(obj):
        # Snapshot attribute types *at add() time* -- session.commit()
        # (called internally by save_symbol_records) expires every
        # instrumented attribute, and a later access silently re-queries
        # SQLite, which would hide exactly the numpy leak this test
        # exists to catch (same reasoning as the V1 test above).
        if type(obj).__name__ == "DecisionV2Snapshot":
            captured.append(
                {
                    "numeric": {f: type(getattr(obj, f)) for f in numeric_fields},
                    "gates": [(type(g["passed"]), type(g["blocking"])) for g in obj.gates],
                    "sub_scores": {k: type(v) for k, v in obj.sub_scores.items() if v is not None},
                }
            )
        return original_add(obj)

    session.add = _spy_add

    await repo.save_symbol_records(session, run.id, [outcome])
    session.add = original_add

    assert len(captured) == 1
    snapshot = captured[0]
    for field, field_type in snapshot["numeric"].items():
        assert field_type is float, f"DecisionV2Snapshot.{field} was {field_type!r}, expected plain float"
    for passed_type, blocking_type in snapshot["gates"]:
        assert passed_type is bool, f"gate 'passed' was {passed_type!r}, expected plain bool"
        assert blocking_type is bool, f"gate 'blocking' was {blocking_type!r}, expected plain bool"
    for field, field_type in snapshot["sub_scores"].items():
        assert field_type is float, f"sub_scores.{field} was {field_type!r}, expected plain float"

    # The row must also be genuinely insertable end-to-end -- proves the
    # coercion actually fixes the crash, not just the attribute types.
    reloaded = session.query(DecisionV2Snapshot).filter_by(symbol="2222").one()
    assert reloaded.scan_run_id == run.id
    assert reloaded.decision == "BUY_CANDIDATE"
    # Phase 2A/2C fields must reach the scan-pipeline row too, not just
    # the single-row /decision-v2 route insert -- both write sites share
    # the same previously-incomplete field list (see decision_v2_snapshot.py).
    assert reloaded.entry_status == decision_v2.entry_status.value
    assert reloaded.risk_level == decision_v2.risk_level
    assert reloaded.technical_evidence == decision_v2.technical_evidence
    assert reloaded.decision_summary_ar == decision_v2.decision_summary_ar
    assert reloaded.market_risk_state == decision_v2.market_risk_state
    assert float(reloaded.best_entry_price) == pytest.approx(float(decision_v2.best_entry_price))


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


@pytest.mark.asyncio
async def test_save_symbol_records_populates_expires_at_from_time_horizon(session, repo):
    """Repository hardening: RecommendationSnapshot.expires_at is
    computed from the decision's own TimeHorizon at write time (see
    get_expiration_days_short_term/_medium_term/_long_term)."""
    from src.analysis.decision.types import TimeHorizon

    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    decision = make_decision(symbol="2222", time_horizon=TimeHorizon.SHORT_TERM)
    outcome = make_outcome(symbol="2222", decision=decision)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = session.query(RecommendationSnapshot).filter_by(symbol="2222").one()
    assert snapshot.expires_at is not None
    delta_days = (snapshot.expires_at - snapshot.evaluated_at).days
    assert delta_days == 14  # get_expiration_days_short_term() default


@pytest.mark.asyncio
async def test_save_symbol_records_populates_target_price_2_and_3_from_decision_v2(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    decision_v2 = make_decision_v2_result(symbol="2222")
    outcome = make_outcome(symbol="2222", decision_v2=decision_v2)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = session.query(RecommendationSnapshot).filter_by(symbol="2222").one()
    assert float(snapshot.target_price_2) == pytest.approx(28.3)
    assert float(snapshot.target_price_3) == pytest.approx(29.0)


@pytest.mark.asyncio
async def test_save_symbol_records_leaves_target_price_2_and_3_null_without_decision_v2(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", decision_v2=None)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = session.query(RecommendationSnapshot).filter_by(symbol="2222").one()
    assert snapshot.target_price_2 is None
    assert snapshot.target_price_3 is None


@pytest.mark.asyncio
async def test_save_symbol_records_threads_bars_used_spread_and_suspension_from_context(session, repo):
    """`context.extra`'s bars_used/likely_suspended/quote(bid/ask) --
    populated by context_builder.py's real quality-gate signals -- are
    persisted alongside the recommendation they gated, for later audit
    (see the migration's own docstring)."""
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    context = AnalysisContext(
        symbol="2222",
        extra={"bars_used": 120, "likely_suspended": False, "quote": {"bid": 100.0, "ask": 100.5}},
    )
    outcome = make_outcome(symbol="2222", context=context)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = session.query(RecommendationSnapshot).filter_by(symbol="2222").one()
    assert snapshot.bars_used == 120
    assert snapshot.likely_suspended is False
    assert float(snapshot.spread_pct) == pytest.approx(0.5, abs=0.01)


@pytest.mark.asyncio
async def test_save_symbol_records_without_context_leaves_gate_signal_columns_null(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222", context=None)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = session.query(RecommendationSnapshot).filter_by(symbol="2222").one()
    assert snapshot.bars_used is None
    assert snapshot.likely_suspended is None
    assert snapshot.spread_pct is None


@pytest.mark.asyncio
async def test_save_symbol_records_applies_active_confidence_calibration(session, repo):
    """When an active ConfidenceCalibrationEngine model exists,
    get_effective_confidence's output is persisted on the snapshot --
    the one real wiring point between E3's calibration engine and the
    live pipeline."""
    import random
    from datetime import date, timedelta

    from src.ai_evolution.confidence_calibration import ConfidenceCalibrationEngine
    from src.domain.models import RecommendationOutcome, RecommendationOutcomeStatus

    stock = _seed_stock(session, "2222")
    rng = random.Random(42)
    for i in range(100):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
        seed_snapshot = RecommendationSnapshot(
            stock_id=stock.id, symbol="2222", evaluated_at=evaluated_at,
            market_price_at_evaluation=100.0, recommendation=RecommendationLabel.BUY,
            total_score=60.0, confidence_score=85.0, target_price=110.0, stop_loss=90.0,
            engine_version="1.0.0", source="live_scan",
        )
        session.add(seed_snapshot)
        session.flush()
        session.add(
            RecommendationOutcome(
                snapshot_id=seed_snapshot.id, symbol="2222", evaluation_horizon_days=7,
                due_at=evaluated_at + timedelta(days=7),
                status=RecommendationOutcomeStatus.SUCCESSFUL if rng.random() < 0.5 else RecommendationOutcomeStatus.FAILED,
                evaluated_at=evaluated_at + timedelta(days=7),
            )
        )
    session.commit()

    engine = ConfidenceCalibrationEngine()
    model = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)
    engine.test(session, model.version)
    engine.activate(session, model.version)

    run = repo.create_scan_run(session, symbols_requested=1)
    decision = make_decision(symbol="2222", confidence=85.0)
    outcome = make_outcome(symbol="2222", decision=decision)

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = (
        session.query(RecommendationSnapshot)
        .filter_by(symbol="2222", run_id=None)
        .order_by(RecommendationSnapshot.id.desc())
        .first()
    )
    assert snapshot.calibrated_confidence_score is not None
    assert 0.0 <= float(snapshot.calibrated_confidence_score) <= 1.0
    assert snapshot.calibration_version == model.version


@pytest.mark.asyncio
async def test_save_symbol_records_no_active_calibration_leaves_calibrated_score_null(session, repo):
    _seed_stock(session, "2222")
    run = repo.create_scan_run(session, symbols_requested=1)
    outcome = make_outcome(symbol="2222")

    await repo.save_symbol_records(session, run.id, [outcome])

    snapshot = session.query(RecommendationSnapshot).filter_by(symbol="2222").one()
    assert snapshot.calibrated_confidence_score is None


@pytest.mark.asyncio
async def test_save_symbol_records_suppresses_a_materially_identical_duplicate(session, repo):
    """Duplicate suppression: a second live scan for the same symbol,
    within the suppression window, with the same direction and
    target/stop within tolerance, does not write a second
    RecommendationSnapshot -- prevents Live Market Mode's frequent
    polling from flooding the outcome-tracked audit table with
    near-identical rows (see get_duplicate_suppression_window_hours)."""
    _seed_stock(session, "2222")
    run_1 = repo.create_scan_run(session, symbols_requested=1)
    now = datetime.now(timezone.utc)
    decision_1 = make_decision(symbol="2222", target_price=105.0, stop_loss=97.0)
    object.__setattr__(decision_1, "generated_at", now)
    outcome_1 = make_outcome(symbol="2222", decision=decision_1)
    await repo.save_symbol_records(session, run_1.id, [outcome_1])

    run_2 = repo.create_scan_run(session, symbols_requested=1)
    decision_2 = make_decision(symbol="2222", target_price=105.2, stop_loss=97.1)  # within 0.5% tolerance
    object.__setattr__(decision_2, "generated_at", now + timedelta(hours=1))
    outcome_2 = make_outcome(symbol="2222", decision=decision_2)
    await repo.save_symbol_records(session, run_2.id, [outcome_2])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").all()
    assert len(snapshots) == 1

    # SymbolIntelligenceRecord (this run's own display row) is still
    # written every scan, unaffected by RecommendationSnapshot dedup.
    from src.domain.models import SymbolIntelligenceRecord

    assert session.query(SymbolIntelligenceRecord).filter_by(symbol="2222").count() == 2


@pytest.mark.asyncio
async def test_save_symbol_records_does_not_suppress_a_materially_different_call(session, repo):
    """A call whose direction or price plan actually changed is never
    suppressed, regardless of how recently the prior one was
    published."""
    _seed_stock(session, "2222")
    run_1 = repo.create_scan_run(session, symbols_requested=1)
    now = datetime.now(timezone.utc)
    decision_1 = make_decision(symbol="2222", target_price=105.0, stop_loss=97.0)
    object.__setattr__(decision_1, "generated_at", now)
    outcome_1 = make_outcome(symbol="2222", decision=decision_1)
    await repo.save_symbol_records(session, run_1.id, [outcome_1])

    run_2 = repo.create_scan_run(session, symbols_requested=1)
    decision_2 = make_decision(symbol="2222", target_price=120.0, stop_loss=97.0)  # target moved well beyond tolerance
    object.__setattr__(decision_2, "generated_at", now + timedelta(hours=1))
    outcome_2 = make_outcome(symbol="2222", decision=decision_2)
    await repo.save_symbol_records(session, run_2.id, [outcome_2])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").order_by(RecommendationSnapshot.id).all()
    assert len(snapshots) == 2


@pytest.mark.asyncio
async def test_save_symbol_records_does_not_suppress_outside_the_window(session, repo, monkeypatch):
    monkeypatch.setattr(repository_module, "get_duplicate_suppression_window_hours", lambda: 24.0)
    _seed_stock(session, "2222")
    run_1 = repo.create_scan_run(session, symbols_requested=1)
    now = datetime.now(timezone.utc)
    decision_1 = make_decision(symbol="2222", target_price=105.0, stop_loss=97.0)
    object.__setattr__(decision_1, "generated_at", now - timedelta(hours=25))
    outcome_1 = make_outcome(symbol="2222", decision=decision_1)
    await repo.save_symbol_records(session, run_1.id, [outcome_1])

    run_2 = repo.create_scan_run(session, symbols_requested=1)
    decision_2 = make_decision(symbol="2222", target_price=105.0, stop_loss=97.0)
    object.__setattr__(decision_2, "generated_at", now)
    outcome_2 = make_outcome(symbol="2222", decision=decision_2)
    await repo.save_symbol_records(session, run_2.id, [outcome_2])

    snapshots = session.query(RecommendationSnapshot).filter_by(symbol="2222").order_by(RecommendationSnapshot.id).all()
    assert len(snapshots) == 2


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


@pytest.mark.asyncio
async def test_get_market_breadth_all_hold_produces_zero_buy_and_sell_counts(session, repo):
    """Phase 2I adversarial case: a real scan run where every symbol
    came back HOLD (no BUY/SELL signal at all) is a legitimate result
    -- the aggregate must report buy_count=0/sell_count=0 rather than
    dropping the run or erroring, and classify_market_risk (a pure
    function, tested with hand-built fixtures elsewhere) must accept
    this real zero/zero breadth and resolve the undefined ratio to
    NEUTRAL rather than raising or dividing by zero."""
    from src.analysis.decision_v2.market_risk import MarketRiskState, classify_market_risk

    symbols = [f"70{i:02d}" for i in range(20)]  # >= the 15-symbol classification floor
    for symbol in symbols:
        _seed_stock(session, symbol)
    run = repo.create_scan_run(session, symbols_requested=len(symbols))
    outcomes = [
        make_outcome(symbol=s, decision=make_decision(symbol=s, recommendation=Recommendation.HOLD, confidence=55.0))
        for s in symbols
    ]
    await repo.save_symbol_records(session, run.id, outcomes)

    breadth = repo.get_market_breadth(session, run.id)

    assert breadth is not None
    assert breadth.buy_count == 0
    assert breadth.sell_count == 0
    assert breadth.symbols_scanned == 20

    assessment = classify_market_risk(market_is_open=True, breadth=breadth)
    assert assessment.state == MarketRiskState.NEUTRAL


def test_get_market_breadth_returns_none_for_a_run_with_no_records(session, repo):
    run = repo.create_scan_run(session, symbols_requested=1)
    assert repo.get_market_breadth(session, run.id) is None


def test_get_market_breadth_returns_none_for_an_unknown_run_id(session, repo):
    assert repo.get_market_breadth(session, 9999) is None
