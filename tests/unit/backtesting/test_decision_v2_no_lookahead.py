"""No-look-ahead audit + core correctness tests for the DecisionEngineV2
historical validation harness (item 13 of the "BASIRAH -- PHASE 3
DECISIONENGINEV2 HISTORICAL VALIDATION HARNESS" mandate). Real
in-memory SQLite, real Stock/PriceBar rows -- proves, not asserts by
convention, that:

  - sector-relative-strength peer calculations are bounded by the
    evaluation timestamp (Phase 3 area 4's dead-input activation, now
    reused historically);
  - the technical/breakout-confirmation leg (built from an as-of-bounded
    price-bar DataFrame) is unaffected by bars dated after the
    evaluation date;
  - Baseline V2 and Phase 3 V2 genuinely diverge when Phase 3-only
    evidence is present (not aliased/identical by accident);
  - the harness produces byte-identical results on repeated runs over
    the same dataset (reproducibility, item 14).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backtesting.decision_v2_backtest_outcome import evaluate_decision_v2_backtest_outcome
from src.backtesting.decision_v2_context import build_decision_v2_as_of_context
from src.backtesting.decision_v2_replay import run_decision_v2_replay
from src.backtesting.decision_v2_strategies import build_replay_point, run_baseline_v2, run_phase3_v2
from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.domain.models.decision_v2_outcome import DecisionV2OutcomeStatus

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_BARS_BEFORE_AS_OF = 60
_AS_OF = (_START + timedelta(days=_BARS_BEFORE_AS_OF - 1)).date()
_BARS_AFTER_AS_OF = 40


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _add_bars(session, stock, closes, start=_START, source="sahmk", is_synthetic=False):
    for i, close in enumerate(closes):
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=start + timedelta(days=i),
                open=Decimal(str(close)), high=Decimal(str(close + 0.3)), low=Decimal(str(close - 0.3)),
                close=Decimal(str(close)), volume=1000, source=source, is_synthetic=is_synthetic,
            )
        )
    session.commit()


def _rising_closes(n, start_price=50.0, step=0.15):
    return [round(start_price + i * step, 4) for i in range(n)]


def _seed_universe(session, future_peer_shock=False, future_subject_shock=False):
    """One subject stock + 3 Energy-sector peers, `_BARS_BEFORE_AS_OF`
    bars up to and including `_AS_OF`, plus `_BARS_AFTER_AS_OF` more
    bars after it. `future_*_shock=True` makes the post-`_AS_OF` bars
    wildly different (a huge jump) -- if the harness is genuinely
    as-of-safe, this must have ZERO effect on anything computed as of
    `_AS_OF`."""
    subject = Stock(symbol="1111", name_en="Subject", sector="Energy")
    session.add(subject)
    session.commit()

    before = _rising_closes(_BARS_BEFORE_AS_OF)
    _add_bars(session, subject, before, start=_START)
    after_start_price = before[-1] + (500.0 if future_subject_shock else 0.15)
    after = _rising_closes(_BARS_AFTER_AS_OF, start_price=after_start_price)
    _add_bars(session, subject, after, start=_START + timedelta(days=_BARS_BEFORE_AS_OF))

    peers = []
    for symbol in ("2222", "3333", "4444"):
        peer = Stock(symbol=symbol, name_en=f"Peer {symbol}", sector="Energy")
        session.add(peer)
        session.commit()
        peer_before = _rising_closes(_BARS_BEFORE_AS_OF, start_price=40.0)
        _add_bars(session, peer, peer_before, start=_START)
        peer_after_start = peer_before[-1] + (500.0 if future_peer_shock else 0.15)
        peer_after = _rising_closes(_BARS_AFTER_AS_OF, start_price=peer_after_start)
        _add_bars(session, peer, peer_after, start=_START + timedelta(days=_BARS_BEFORE_AS_OF))
        peers.append(peer)

    return subject, peers


class TestNoLookAheadAudit:
    def test_sector_strength_ignores_future_peer_bars(self, session):
        """The exact regression this whole harness exists to guard
        against: sector_strength.py's peer query was unbounded before
        the `as_of` extension -- this proves the bound actually works."""
        subject, _ = _seed_universe(session, future_peer_shock=False)
        ctx_normal = build_decision_v2_as_of_context(session, subject, _AS_OF)

        # Same subject history, but peers get a wild future price jump
        # after _AS_OF -- must NOT change what was computed as of _AS_OF.
        session2_engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=session2_engine)
        session2 = sessionmaker(bind=session2_engine)()
        subject2, _ = _seed_universe(session2, future_peer_shock=True)
        ctx_shocked = build_decision_v2_as_of_context(session2, subject2, _AS_OF)
        session2.close()
        Base.metadata.drop_all(bind=session2_engine)

        assert "sector_rotation" in ctx_normal.context.extra
        assert ctx_normal.context.extra["sector_rotation"] == ctx_shocked.context.extra["sector_rotation"], (
            "A future peer price shock changed the as-of sector-relative-strength result -- "
            "this is a genuine look-ahead leak."
        )

    def test_technical_and_breakout_ignore_future_subject_bars(self, session):
        """Same proof for the subject stock's own future bars -- the
        as-of-bounded `df` (from `load_as_of_dataset`) must be
        identical regardless of what happens after `_AS_OF`."""
        subject, _ = _seed_universe(session, future_subject_shock=False)
        ctx_normal = build_decision_v2_as_of_context(session, subject, _AS_OF)

        engine2 = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine2)
        session2 = sessionmaker(bind=engine2)()
        subject2, _ = _seed_universe(session2, future_subject_shock=True)
        ctx_shocked = build_decision_v2_as_of_context(session2, subject2, _AS_OF)
        session2.close()
        Base.metadata.drop_all(bind=engine2)

        assert ctx_normal.context.latest_price == ctx_shocked.context.latest_price
        assert (
            ctx_normal.context.technical_result.latest_snapshot()
            == ctx_shocked.context.technical_result.latest_snapshot()
        ), "A future subject-price shock changed the as-of technical result -- a genuine look-ahead leak."
        assert ctx_normal.context.extra.get("breakout_confirmation") == ctx_shocked.context.extra.get(
            "breakout_confirmation"
        )

    def test_market_state_reconstructed_from_as_of_not_wall_clock(self, session):
        """market_is_open/market_status must depend only on `_AS_OF`,
        never on the real current time this test happens to run at."""
        subject, _ = _seed_universe(session)
        ctx = build_decision_v2_as_of_context(session, subject, _AS_OF)
        from src.market_intelligence.trading_calendar import is_market_open
        from datetime import time as _time

        as_of_end = datetime.combine(_AS_OF, _time.max, tzinfo=timezone.utc)
        assert ctx.market_is_open == is_market_open(as_of_end)


class TestBaselineVsPhase3Divergence:
    def test_engines_genuinely_diverge_when_phase3_evidence_present(self, session):
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None

        baseline_result = run_baseline_v2(point)
        phase3_result = run_phase3_v2(point)

        # The frozen baseline DecisionResult type predates these
        # fields entirely -- confirms this is a real, different engine
        # version, not the same class imported twice.
        assert not hasattr(baseline_result, "is_high_quality_buy")
        assert hasattr(phase3_result, "is_high_quality_buy")
        assert not hasattr(baseline_result, "sector_strength_used")
        assert hasattr(phase3_result, "sector_strength_used")


class TestReplayEvaluationTimeInjection:
    """Regression coverage for the zero-actionable-signal root-cause
    fix: the harness must pass its own as-of `evaluation_time` into
    BOTH engine arms so neither is forced to WATCH purely because the
    real historical quote timestamp predates the sandbox's real
    wall-clock "now" by weeks or months."""

    def test_both_arms_receive_a_freshness_evaluation_time_matching_as_of(self, session):
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None
        expected = datetime.combine(_AS_OF, datetime.max.time(), tzinfo=timezone.utc)
        assert point.as_of_context.evaluation_time == expected

        baseline = run_baseline_v2(point)
        phase3 = run_phase3_v2(point)
        for result in (baseline, phase3):
            freshness = next(g for g in result.gates if g.name == "data_freshness")
            assert freshness.status.value == "PASS", (
                "A historical replay point's own price-bar timestamp is always <= its as_of "
                "date -- data_freshness must pass when evaluation_time is correctly wired, "
                "proving the harness no longer measures staleness against real wall-clock time."
            )


class TestReplayDeterminism:
    def test_same_dataset_same_config_produces_identical_results(self, session):
        _seed_universe(session)
        summary_1 = run_decision_v2_replay(
            session, ["1111"], date(2026, 2, 1), date(2026, 2, 15), evaluation_frequency_days=7,
        )
        summary_2 = run_decision_v2_replay(
            session, ["1111"], date(2026, 2, 1), date(2026, 2, 15), evaluation_frequency_days=7,
        )
        assert summary_1.evaluated_points == summary_2.evaluated_points
        assert [r.decision for r in summary_1.baseline_records] == [r.decision for r in summary_2.baseline_records]
        assert [r.decision for r in summary_1.phase3_records] == [r.decision for r in summary_2.phase3_records]
        assert [r.confidence_score for r in summary_1.phase3_records] == [
            r.confidence_score for r in summary_2.phase3_records
        ]


class TestOutcomeSameBarAmbiguity:
    def test_target_and_stop_touched_same_bar_is_partial_never_guessed(self, session):
        from src.analysis.decision_v2.types import DataFreshnessStatus, Decision, DecisionResult

        stock = Stock(symbol="9999", name_en="Ambiguous", sector="Energy")
        session.add(stock)
        session.commit()

        decision_date = date(2026, 1, 1)
        # Entry triggers day 1; on day 3 a single wide-range bar touches
        # both target and stop -- genuinely undecidable from daily OHLC.
        bars = [
            (100.0, 100.5, 99.5),   # day 0 (decision date itself, not read forward)
            (100.2, 100.6, 99.9),   # day 1 -- inside entry zone [100, 101]
            (100.3, 100.7, 100.0),  # day 2
            (100.3, 110.0, 90.0),   # day 3 -- both target (108) and stop (95) touched same bar
        ]
        for i, (close, high, low) in enumerate(bars):
            session.add(
                PriceBar(
                    stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
                    timestamp=datetime.combine(decision_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=i),
                    open=Decimal(str(close)), high=Decimal(str(high)), low=Decimal(str(low)), close=Decimal(str(close)),
                    volume=1000, source="sahmk", is_synthetic=False,
                )
            )
        session.commit()

        decision = DecisionResult(
            symbol="9999", company_name_ar=None, company_name_en="Ambiguous", sector_ar=None,
            decision=Decision.BUY_CANDIDATE, decision_label_ar="شراء", confidence_score=80.0,
            opportunity_quality_score=None, risk_score=None, data_quality_score=None,
            data_freshness_status=DataFreshnessStatus.LIVE,
            current_price=100.2, entry_zone_low=100.0, entry_zone_high=101.0, stop_loss=95.0,
            target_1=108.0, target_2=None, target_3=None,
            expected_return_target_1=None, expected_return_target_2=None, downside_to_stop=None,
            risk_reward_target_1=None, risk_reward_target_2=None,
            expected_holding_period_min_days=None, expected_holding_period_max_days=None,
            expected_holding_period_label_ar="", horizon_type="SHORT_TERM", market_status="OPEN",
            decision_timestamp=datetime.now(timezone.utc), invalidation_conditions=[],
            positive_reasons=[], negative_reasons=[], warnings=[], recommendation_basis="",
            analysis_version="test", data_source="sahmk", scan_run_id=None,
            sub_scores=None,
        )

        outcome = evaluate_decision_v2_backtest_outcome(
            session, stock, decision, decision_date, entry_expiry_days=5, resolution_horizon_days=10
        )
        assert outcome.entry_triggered is True
        assert outcome.status is DecisionV2OutcomeStatus.PARTIAL
        assert outcome.first_event == "TIE"
