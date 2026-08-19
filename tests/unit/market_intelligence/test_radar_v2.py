"""Unit tests for the Basirah Radar V2 orchestrator
(src.market_intelligence.radar_v2). Stage 2 is always a fake, injected
runner here -- never the real `_run_one_bounded_background_cycle` (no
FastAPI/Redis/SAHMK involved) -- so every test is deterministic and
proves the orchestration/dedup logic on its own, independent of the
already-tested Stage 2 safety machinery it composes with.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2Snapshot,
    MarketScanRun,
    PriceBar,
    RadarOpportunity,
    Stock,
    Timeframe,
)
from src.market_intelligence.radar_v2 import (
    MINIMUM_SAMPLE_GATE,
    _accumulation_status,
    compute_radar_v2_extended_performance,
    compute_radar_v2_performance,
    emit_radar_opportunities,
    run_radar_v2_cycle,
    select_stage2_candidates,
)
from src.market_intelligence.stage1_local_scan import (
    Stage1ComponentScores,
    Stage1Signal,
    Stage1SymbolResult,
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


def _stock(session, symbol="1111", instrument_bucket=None):
    row = Stock(symbol=symbol, name_en=f"Stock {symbol}", is_active=True, instrument_bucket=instrument_bucket)
    session.add(row)
    session.commit()
    return row


def _candidate(symbol="1111", rank_score=80.0, signals=None):
    return Stage1SymbolResult(
        symbol=symbol,
        is_candidate=True,
        latest_close=100.0,
        ranking_score=rank_score,
        component_scores=Stage1ComponentScores(trend=80.0, momentum=75.0, volume=60.0, liquidity=70.0, volatility=65.0, risk_reward=55.0),
        signals=signals if signals is not None else [Stage1Signal("trending", "اتجاه قوي")],
        risk_reward_ratio=1.8,
    )


def _snapshot(
    session, stock, scan_run_id, decision="BUY_CANDIDATE", confidence=70.0, current_price=100.0,
    market_risk_state=None, sector_ar=None, horizon_type=None, downside_to_stop=None,
):
    row = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        sector_ar=sector_ar,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=confidence,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=current_price,
        market_status="OPEN",
        decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
        scan_run_id=scan_run_id,
        market_risk_state=market_risk_state,
        horizon_type=horizon_type,
        downside_to_stop=downside_to_stop,
    )
    session.add(row)
    session.commit()
    return row


class TestSelectStage2Candidates:
    def test_truncates_to_the_configured_cap(self, monkeypatch):
        monkeypatch.setenv("RADAR_STAGE2_CANDIDATE_CAP", "2")
        candidates = [_candidate(f"{i}") for i in range(5)]
        selected = select_stage2_candidates(candidates)
        assert len(selected) == 2
        assert selected == candidates[:2]

    def test_never_exceeds_cap_even_with_a_tiny_candidate_list(self, monkeypatch):
        monkeypatch.setenv("RADAR_STAGE2_CANDIDATE_CAP", "15")
        candidates = [_candidate("1111")]
        assert select_stage2_candidates(candidates) == candidates


class TestEmitRadarOpportunities:
    def test_creates_one_opportunity_per_matching_snapshot(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1)
        candidate = _candidate(stock.symbol)

        result = emit_radar_opportunities(session, scan_run_id=1, candidates=[candidate])

        assert len(result.emitted) == 1
        assert result.suppressed_symbols == []
        row = result.emitted[0]
        assert row.decision_v2_snapshot_id == snapshot.id
        assert row.classification == "BUY_CANDIDATE"
        assert row.stage1_rank == 1
        assert row.stage1_ranking_score == 80.0
        assert row.stage1_signals == [{"name": "trending", "detail_ar": "اتجاه قوي"}]
        assert row.superseded_by_id is None

    def test_skips_a_candidate_with_no_matching_snapshot(self, session):
        stock = _stock(session)
        candidate = _candidate(stock.symbol)
        # No DecisionV2Snapshot written for scan_run_id=1 -- Stage 2
        # produced nothing for this symbol.
        result = emit_radar_opportunities(session, scan_run_id=1, candidates=[candidate])
        assert result.emitted == []
        assert result.suppressed_symbols == []

    def test_rank_reflects_position_in_the_candidate_list(self, session):
        s1 = _stock(session, "1111")
        s2 = _stock(session, "2222")
        _snapshot(session, s1, scan_run_id=1)
        _snapshot(session, s2, scan_run_id=1)

        result = emit_radar_opportunities(
            session, scan_run_id=1, candidates=[_candidate("1111", 90.0), _candidate("2222", 70.0)]
        )
        by_symbol = {r.symbol: r for r in result.emitted}
        assert by_symbol["1111"].stage1_rank == 1
        assert by_symbol["2222"].stage1_rank == 2


class TestOutcomeTrackingWiring:
    def test_an_actionable_decision_gets_a_pending_outcome_row(self, session):
        stock = _stock(session)
        _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")

        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])

        outcomes = session.query(DecisionV2Outcome).filter_by(symbol=stock.symbol).all()
        assert len(outcomes) == 1
        assert outcomes[0].status.value == "PENDING"

    def test_a_non_actionable_decision_gets_no_outcome_row(self, session):
        stock = _stock(session)
        _snapshot(session, stock, scan_run_id=1, decision="WATCH")

        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])

        assert session.query(DecisionV2Outcome).filter_by(symbol=stock.symbol).count() == 0

    def test_outcome_tracking_still_applies_to_a_suppressed_duplicate(self, session):
        """Dedup suppresses the *displayed* radar card, never the
        underlying real-market outcome measurement."""
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        _snapshot(session, stock, scan_run_id=1, confidence=70.0)
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol, 80.0)], emitted_at=t0)

        snapshot2 = _snapshot(session, stock, scan_run_id=2, confidence=71.0)
        result = emit_radar_opportunities(
            session, 2, [_candidate(stock.symbol, 81.0)], emitted_at=t0 + timedelta(hours=1)
        )
        assert result.suppressed_symbols == [stock.symbol]

        outcomes = session.query(DecisionV2Outcome).filter_by(symbol=stock.symbol).all()
        assert len(outcomes) == 2
        assert {o.decision_v2_snapshot_id for o in outcomes} >= {snapshot2.id}


class TestDeduplication:
    def test_materially_identical_candidate_within_window_is_suppressed(self, session):
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        _snapshot(session, stock, scan_run_id=1, confidence=70.0)
        first = emit_radar_opportunities(session, 1, [_candidate(stock.symbol, 80.0)], emitted_at=t0)
        assert len(first.emitted) == 1
        assert first.emitted[0].superseded_by_id is None

        # Same classification, confidence within the default 5-point
        # threshold, score within the default 3-point threshold, well
        # inside the default 24h window -- must be suppressed.
        _snapshot(session, stock, scan_run_id=2, confidence=71.0)
        second = emit_radar_opportunities(
            session, 2, [_candidate(stock.symbol, 81.0)], emitted_at=t0 + timedelta(hours=1)
        )
        assert second.emitted == []
        assert second.suppressed_symbols == [stock.symbol]

        # The original opportunity is untouched and still live.
        session.refresh(first.emitted[0])
        assert first.emitted[0].superseded_by_id is None

    def test_a_changed_classification_is_never_suppressed_and_supersedes_the_prior_row(self, session):
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        first = emit_radar_opportunities(session, 1, [_candidate(stock.symbol)], emitted_at=t0)
        old_id = first.emitted[0].id

        _snapshot(session, stock, scan_run_id=2, decision="STRONG_BUY_CANDIDATE")
        second = emit_radar_opportunities(
            session, 2, [_candidate(stock.symbol)], emitted_at=t0 + timedelta(minutes=30)
        )

        assert len(second.emitted) == 1
        assert second.suppressed_symbols == []
        session.refresh(first.emitted[0])
        assert first.emitted[0].superseded_by_id == second.emitted[0].id
        assert first.emitted[0].id == old_id
        # The superseded row's own evidence is never rewritten.
        assert first.emitted[0].classification == "BUY_CANDIDATE"

    def test_a_large_score_change_is_never_suppressed(self, session):
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        _snapshot(session, stock, scan_run_id=1, confidence=70.0)
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol, rank_score=50.0)], emitted_at=t0)

        _snapshot(session, stock, scan_run_id=2, confidence=70.0)
        second = emit_radar_opportunities(
            session, 2, [_candidate(stock.symbol, rank_score=95.0)], emitted_at=t0 + timedelta(minutes=30)
        )
        assert len(second.emitted) == 1
        assert second.suppressed_symbols == []

    def test_a_stale_prior_outside_the_window_is_refreshed_even_if_materially_identical(self, session, monkeypatch):
        monkeypatch.setenv("MARKET_DUPLICATE_SUPPRESSION_WINDOW_HOURS", "1")
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        _snapshot(session, stock, scan_run_id=1, confidence=70.0)
        first = emit_radar_opportunities(session, 1, [_candidate(stock.symbol, 80.0)], emitted_at=t0)

        _snapshot(session, stock, scan_run_id=2, confidence=70.0)
        second = emit_radar_opportunities(
            session, 2, [_candidate(stock.symbol, 80.0)], emitted_at=t0 + timedelta(hours=2)
        )
        assert len(second.emitted) == 1
        assert second.suppressed_symbols == []
        session.refresh(first.emitted[0])
        assert first.emitted[0].superseded_by_id == second.emitted[0].id


@dataclass
class _FakeStage2Result:
    executed: bool
    stop_reason: Optional[str] = None
    run_id: Optional[int] = None


class TestRunRadarV2Cycle:
    @pytest.mark.asyncio
    async def test_no_stage1_candidates_never_calls_stage2(self, session):
        calls: List[str] = []

        async def fake_stage2(session_, caller, resolve_symbols):
            calls.append(caller)
            return _FakeStage2Result(executed=True, run_id=1)

        result = await run_radar_v2_cycle(session, fake_stage2)
        assert result.stage2_executed is False
        assert result.stage2_stop_reason == "no_stage1_candidates"
        assert calls == []

    @pytest.mark.asyncio
    async def test_stage2_refusal_is_surfaced_verbatim_with_zero_opportunities(self, session):
        stock = _stock(session)
        # Give this symbol a real Stage-1-worthy volume spike so it
        # becomes a genuine candidate.
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(40):
            close = Decimal("20.0") + (Decimal("0.1") if i % 2 == 0 else Decimal("-0.1"))
            vol = 60_000 if i == 39 else 10_000
            session.add(
                PriceBar(
                    stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
                    timestamp=base + timedelta(days=i),
                    open=close, high=close + Decimal("0.2"), low=close - Decimal("0.2"),
                    close=close, volume=vol,
                )
            )
        session.commit()

        async def fake_stage2(session_, caller, resolve_symbols):
            assert resolve_symbols() == [stock.symbol]
            return _FakeStage2Result(executed=False, stop_reason="background_quota_low")

        result = await run_radar_v2_cycle(session, fake_stage2)
        assert result.stage2_executed is False
        assert result.stage2_stop_reason == "background_quota_low"
        assert result.opportunities_emitted == []
        assert session.query(RadarOpportunity).count() == 0

    @pytest.mark.asyncio
    async def test_a_successful_stage2_run_emits_opportunities(self, session):
        stock = _stock(session)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(40):
            close = Decimal("20.0") + (Decimal("0.1") if i % 2 == 0 else Decimal("-0.1"))
            vol = 60_000 if i == 39 else 10_000
            session.add(
                PriceBar(
                    stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
                    timestamp=base + timedelta(days=i),
                    open=close, high=close + Decimal("0.2"), low=close - Decimal("0.2"),
                    close=close, volume=vol,
                )
            )
        session.commit()

        run = MarketScanRun(symbols_requested=1)
        session.add(run)
        session.commit()

        async def fake_stage2(session_, caller, resolve_symbols):
            symbols = resolve_symbols()
            for sym in symbols:
                _snapshot(session_, stock, scan_run_id=run.id)
            return _FakeStage2Result(executed=True, run_id=run.id)

        result = await run_radar_v2_cycle(session, fake_stage2)
        assert result.stage2_executed is True
        assert result.scan_run_id == run.id
        assert len(result.opportunities_emitted) == 1
        assert result.opportunities_emitted[0].symbol == stock.symbol
        assert session.query(RadarOpportunity).count() == 1

        # RADAR-Phase1 (43-phase mandate): Stage 1's real funnel numbers
        # must be persisted onto the MarketScanRun row this cycle used,
        # not just held in-memory and discarded -- this is what lets a
        # later read-only route report "scanned N locally, ranked M
        # candidates" honestly.
        session.refresh(run)
        assert run.stage1_universe_size == result.stage1_universe_size
        assert run.stage1_candidate_count == result.stage1_candidate_count
        assert run.stage1_candidate_count == 1  # the one real candidate built above
        assert run.stage1_evaluated_count == 1  # the single symbol had enough history to be scored


class TestAccumulationStatus:
    """Post-VAL-8 accumulation phase: the explicit, statistically
    defensible minimum-sample gate (reused from the platform's own
    DEFAULT_MIN_SAMPLE_SIZE=30, not an arbitrary new number) before
    optimization/calibration may begin."""

    def test_minimum_sample_gate_is_the_platforms_existing_statistical_floor(self):
        assert MINIMUM_SAMPLE_GATE == 30

    def test_zero_resolved_is_insufficient_data(self):
        assert _accumulation_status(0) == "INSUFFICIENT_DATA"

    def test_below_gate_is_preliminary(self):
        assert _accumulation_status(1) == "PRELIMINARY"
        assert _accumulation_status(MINIMUM_SAMPLE_GATE - 1) == "PRELIMINARY"

    def test_at_or_above_gate_is_ready_for_calibration(self):
        assert _accumulation_status(MINIMUM_SAMPLE_GATE) == "READY_FOR_CALIBRATION"
        assert _accumulation_status(MINIMUM_SAMPLE_GATE + 100) == "READY_FOR_CALIBRATION"


class TestComputeRadarV2Performance:
    def test_empty_database_reports_none_rates_not_zero(self, session):
        metrics = compute_radar_v2_performance(session)
        assert metrics.total_opportunities_emitted == 0
        assert metrics.resolved_count == 0
        assert metrics.target_hit_rate is None
        assert metrics.stop_loss_hit_rate is None
        assert metrics.average_return_pct is None
        assert metrics.minimum_sample_size_required == MINIMUM_SAMPLE_GATE
        assert metrics.sample_size_adequate is False
        assert metrics.accumulation_status == "INSUFFICIENT_DATA"

    def test_pending_actionable_opportunity_is_tracked_but_not_resolved(self, session):
        stock = _stock(session)
        _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])

        metrics = compute_radar_v2_performance(session)
        assert metrics.total_opportunities_emitted == 1
        assert metrics.total_outcomes_tracked == 1
        assert metrics.pending_count == 1
        assert metrics.resolved_count == 0
        assert metrics.target_hit_rate is None

    def test_live_opportunities_by_classification_counts_only_non_superseded_rows(self, session):
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)], emitted_at=t0)

        _snapshot(session, stock, scan_run_id=2, decision="STRONG_BUY_CANDIDATE")
        emit_radar_opportunities(session, 2, [_candidate(stock.symbol)], emitted_at=t0 + timedelta(hours=1))

        metrics = compute_radar_v2_performance(session)
        # The first BUY_CANDIDATE row was superseded -- only the live
        # STRONG_BUY_CANDIDATE one counts toward the current composition.
        assert metrics.live_opportunities_by_classification == {"STRONG_BUY_CANDIDATE": 1}
        assert metrics.total_opportunities_emitted == 2

    def test_resolved_outcomes_compute_real_rates(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])

        outcome = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        outcome.status = "TARGET_1_HIT"
        outcome.return_pct = 8.5
        session.commit()

        metrics = compute_radar_v2_performance(session)
        assert metrics.resolved_count == 1
        assert metrics.target_hit_count == 1
        assert metrics.target_hit_rate == 1.0
        assert metrics.stop_loss_hit_rate == 0.0
        assert metrics.average_return_pct == 8.5
        # 1 resolved outcome is real signal, but far below the 30-sample
        # gate -- honestly PRELIMINARY, not treated as calibration-ready.
        assert metrics.sample_size_adequate is False
        assert metrics.accumulation_status == "PRELIMINARY"


class TestComputeRadarV2ExtendedPerformance:
    """RADAR-C Phase D: the mandate's explicit breakdown questions
    (win rate by classification/confidence-band/market-regime,
    performance by sector/horizon, MFE/MAE, calibration) over the full
    RadarOpportunity/DecisionV2Outcome history."""

    def test_empty_database_reports_empty_groups_and_none_aggregates(self, session):
        metrics = compute_radar_v2_extended_performance(session)
        assert metrics.win_rate_by_classification == []
        assert metrics.average_return_pct is None
        assert metrics.median_return_pct is None
        assert metrics.expected_calibration_error is None

    def test_pending_outcome_is_excluded_from_every_breakdown(self, session):
        stock = _stock(session)
        _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=75.0)
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])

        metrics = compute_radar_v2_extended_performance(session)
        # The group still appears (a real signal was issued) but its
        # win_rate is honestly None, not a fabricated 0% or 100% --
        # PENDING is neither a win nor a loss yet, matching the same
        # discipline validation_metrics.py already applies.
        assert len(metrics.win_rate_by_classification) == 1
        assert metrics.win_rate_by_classification[0].signal_count == 1
        assert metrics.win_rate_by_classification[0].win_rate is None

    def test_target_hit_and_stop_hit_split_by_classification(self, session):
        stock_a = _stock(session, symbol="1111")
        stock_b = _stock(session, symbol="2222")

        snap_a = _snapshot(session, stock_a, scan_run_id=1, decision="BUY_CANDIDATE", confidence=72.0)
        emit_radar_opportunities(session, 1, [_candidate(stock_a.symbol)])
        outcome_a = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_a.id).one()
        outcome_a.status = "TARGET_1_HIT"
        outcome_a.return_pct = 6.0
        outcome_a.max_favorable_excursion_pct = 7.5
        outcome_a.max_adverse_excursion_pct = -1.0

        snap_b = _snapshot(session, stock_b, scan_run_id=2, decision="STRONG_BUY_CANDIDATE", confidence=88.0)
        emit_radar_opportunities(session, 2, [_candidate(stock_b.symbol)])
        outcome_b = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_b.id).one()
        outcome_b.status = "STOP_LOSS_HIT"
        outcome_b.return_pct = -4.0
        outcome_b.max_favorable_excursion_pct = 1.0
        outcome_b.max_adverse_excursion_pct = -4.5
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)

        by_class = {g.label: g for g in metrics.win_rate_by_classification}
        assert by_class["BUY_CANDIDATE"].win_rate == 1.0
        assert by_class["STRONG_BUY_CANDIDATE"].win_rate == 0.0

        by_band = {g.label: g for g in metrics.win_rate_by_confidence_band}
        assert by_band["70-79"].win_rate == 1.0
        assert by_band["80-89"].win_rate == 0.0

        assert metrics.average_return_pct == pytest.approx(1.0)  # (6.0 + -4.0) / 2
        assert metrics.median_return_pct == pytest.approx(1.0)
        assert metrics.average_favorable_excursion_pct == pytest.approx(4.25)
        assert metrics.average_adverse_excursion_pct == pytest.approx(-2.75)
        assert metrics.calibration_pair_count == 2
        # 1 resolved outcome per classification cohort -- real signal,
        # but nowhere near the 30-sample gate.
        assert by_class["BUY_CANDIDATE"].sample_size_adequate is False
        assert by_class["STRONG_BUY_CANDIDATE"].sample_size_adequate is False

    def test_group_sample_size_adequate_flips_true_at_the_gate(self, session):
        # Distinct symbols -- avoids the dedup/supersession window
        # entirely, so all MINIMUM_SAMPLE_GATE rows really land as
        # separate, independently-resolved outcomes.
        for i in range(MINIMUM_SAMPLE_GATE):
            stock = _stock(session, symbol=f"{1000 + i}")
            snap = _snapshot(session, stock, scan_run_id=i + 1, decision="BUY_CANDIDATE", confidence=70.0)
            emit_radar_opportunities(session, i + 1, [_candidate(stock.symbol)])
            outcome = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap.id).one()
            outcome.status = "TARGET_1_HIT"
            outcome.return_pct = 5.0
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)
        group = {g.label: g for g in metrics.win_rate_by_classification}["BUY_CANDIDATE"]
        assert group.resolved_count == MINIMUM_SAMPLE_GATE
        assert group.sample_size_adequate is True

    def test_groups_by_market_regime_sector_and_horizon(self, session):
        stock = _stock(session)
        snapshot = _snapshot(
            session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0,
            market_risk_state="STRONG_ENTRY", sector_ar="الطاقة", horizon_type="SHORT_TERM",
        )
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])
        outcome = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        outcome.status = "TARGET_1_HIT"
        outcome.return_pct = 5.0
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)
        assert {g.label for g in metrics.win_rate_by_market_regime} == {"STRONG_ENTRY"}
        assert {g.label for g in metrics.performance_by_sector} == {"الطاقة"}
        assert {g.label for g in metrics.performance_by_holding_horizon} == {"SHORT_TERM"}

    def test_superseded_opportunities_still_count_toward_breakdowns(self, session):
        # Unlike compute_radar_v2_performance's live_opportunities_by_
        # classification (current composition only), the extended
        # breakdowns are historical -- a superseded opportunity's real
        # resolved outcome must still be counted.
        stock = _stock(session)
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        snap_1 = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=71.0)
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)], emitted_at=t0)
        outcome_1 = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_1.id).one()
        outcome_1.status = "TARGET_1_HIT"
        outcome_1.return_pct = 3.0
        session.commit()

        _snapshot(session, stock, scan_run_id=2, decision="STRONG_BUY_CANDIDATE", confidence=90.0)
        emit_radar_opportunities(session, 2, [_candidate(stock.symbol)], emitted_at=t0 + timedelta(hours=1))

        metrics = compute_radar_v2_extended_performance(session)
        by_class = {g.label: g for g in metrics.win_rate_by_classification}
        assert "BUY_CANDIDATE" in by_class
        assert by_class["BUY_CANDIDATE"].win_rate == 1.0

    def test_total_signals_by_classification_counts_every_emitted_opportunity_including_non_actionable(self, session):
        stock_a = _stock(session, symbol="1111")
        stock_b = _stock(session, symbol="2222")
        # WATCH is non-actionable -- gets a RadarOpportunity row but no
        # DecisionV2Outcome, so it must never appear in win_rate_by_
        # classification, yet it must still be counted here.
        _snapshot(session, stock_a, scan_run_id=1, decision="WATCH", confidence=55.0)
        emit_radar_opportunities(session, 1, [_candidate(stock_a.symbol)])

        _snapshot(session, stock_b, scan_run_id=2, decision="BUY_CANDIDATE", confidence=75.0)
        emit_radar_opportunities(session, 2, [_candidate(stock_b.symbol)])

        metrics = compute_radar_v2_extended_performance(session)
        assert metrics.total_signals_by_classification == {"WATCH": 1, "BUY_CANDIDATE": 1}
        assert {g.label for g in metrics.win_rate_by_classification} == {"BUY_CANDIDATE"}

    def test_resolved_and_unresolved_counts_and_hit_rates_use_the_resolved_denominator(self, session):
        stock_a = _stock(session, symbol="1111")
        stock_b = _stock(session, symbol="2222")
        stock_c = _stock(session, symbol="3333")

        snap_a = _snapshot(session, stock_a, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0)
        emit_radar_opportunities(session, 1, [_candidate(stock_a.symbol)])
        outcome_a = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_a.id).one()
        outcome_a.status = "TARGET_1_HIT"
        outcome_a.return_pct = 5.0

        snap_b = _snapshot(session, stock_b, scan_run_id=2, decision="BUY_CANDIDATE", confidence=71.0)
        emit_radar_opportunities(session, 2, [_candidate(stock_b.symbol)])
        outcome_b = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_b.id).one()
        outcome_b.status = "STOP_LOSS_HIT"
        outcome_b.return_pct = -3.0

        # Still PENDING -- unresolved, must not count toward either
        # denominator.
        _snapshot(session, stock_c, scan_run_id=3, decision="BUY_CANDIDATE", confidence=72.0)
        emit_radar_opportunities(session, 3, [_candidate(stock_c.symbol)])
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)
        group = {g.label: g for g in metrics.win_rate_by_classification}["BUY_CANDIDATE"]
        assert group.signal_count == 3
        assert group.resolved_count == 2
        assert group.unresolved_count == 1
        assert group.target_hit_rate == pytest.approx(0.5)
        assert group.stop_loss_hit_rate == pytest.approx(0.5)
        assert group.win_rate == pytest.approx(0.5)
        assert group.max_adverse_outcome_pct == pytest.approx(-3.0)

    def test_average_risk_reward_realized_divides_return_by_planned_risk(self, session):
        stock = _stock(session)
        # Planned entry-to-stop risk of 2% at signal time; realized a 6%
        # return -- a 3.0 R-multiple.
        snapshot = _snapshot(
            session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0, downside_to_stop=2.0,
        )
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])
        outcome = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        outcome.status = "TARGET_1_HIT"
        outcome.return_pct = 6.0
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)
        group = {g.label: g for g in metrics.win_rate_by_classification}["BUY_CANDIDATE"]
        assert group.average_risk_reward_realized == pytest.approx(3.0)
        assert group.expectancy_pct == pytest.approx(6.0)

    def test_average_risk_reward_realized_is_none_without_planned_risk(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0)
        emit_radar_opportunities(session, 1, [_candidate(stock.symbol)])
        outcome = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        outcome.status = "TARGET_1_HIT"
        outcome.return_pct = 6.0
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)
        group = {g.label: g for g in metrics.win_rate_by_classification}["BUY_CANDIDATE"]
        assert group.average_risk_reward_realized is None

    def test_performance_by_market_segments_main_market_vs_nomu_vs_unknown(self, session):
        main_stock = _stock(session, symbol="1111", instrument_bucket="MAIN_MARKET_EQUITY")
        nomu_stock = _stock(session, symbol="9999", instrument_bucket="NOMU_EQUITY")
        unknown_stock = _stock(session, symbol="5555", instrument_bucket=None)

        snap_main = _snapshot(session, main_stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0)
        emit_radar_opportunities(session, 1, [_candidate(main_stock.symbol)])
        outcome_main = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_main.id).one()
        outcome_main.status = "TARGET_1_HIT"
        outcome_main.return_pct = 4.0

        snap_nomu = _snapshot(session, nomu_stock, scan_run_id=2, decision="BUY_CANDIDATE", confidence=71.0)
        emit_radar_opportunities(session, 2, [_candidate(nomu_stock.symbol)])
        outcome_nomu = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_nomu.id).one()
        outcome_nomu.status = "STOP_LOSS_HIT"
        outcome_nomu.return_pct = -2.0

        snap_unknown = _snapshot(session, unknown_stock, scan_run_id=3, decision="BUY_CANDIDATE", confidence=72.0)
        emit_radar_opportunities(session, 3, [_candidate(unknown_stock.symbol)])
        outcome_unknown = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snap_unknown.id).one()
        outcome_unknown.status = "TARGET_1_HIT"
        outcome_unknown.return_pct = 1.0
        session.commit()

        metrics = compute_radar_v2_extended_performance(session)
        by_market = {g.label: g for g in metrics.performance_by_market}
        assert set(by_market) == {"Main Market", "Nomu", "Unknown"}
        assert by_market["Main Market"].signal_count == 1
        assert by_market["Nomu"].signal_count == 1
        assert by_market["Unknown"].signal_count == 1
        assert by_market["Main Market"].win_rate == 1.0
        assert by_market["Nomu"].win_rate == 0.0
