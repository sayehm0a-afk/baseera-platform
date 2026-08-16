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
from src.domain.models import DecisionV2Outcome, DecisionV2Snapshot, PriceBar, RadarOpportunity, Stock, Timeframe
from src.market_intelligence.radar_v2 import (
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


def _stock(session, symbol="1111"):
    row = Stock(symbol=symbol, name_en=f"Stock {symbol}", is_active=True)
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


def _snapshot(session, stock, scan_run_id, decision="BUY_CANDIDATE", confidence=70.0, current_price=100.0):
    row = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
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

        async def fake_stage2(session_, caller, resolve_symbols):
            symbols = resolve_symbols()
            run_id = 42
            for sym in symbols:
                _snapshot(session_, stock, scan_run_id=run_id)
            return _FakeStage2Result(executed=True, run_id=run_id)

        result = await run_radar_v2_cycle(session, fake_stage2)
        assert result.stage2_executed is True
        assert result.scan_run_id == 42
        assert len(result.opportunities_emitted) == 1
        assert result.opportunities_emitted[0].symbol == stock.symbol
        assert session.query(RadarOpportunity).count() == 1
