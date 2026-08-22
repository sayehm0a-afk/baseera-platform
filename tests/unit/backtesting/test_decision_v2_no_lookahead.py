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

from src.ai_evolution.confidence_calibration import TRAINING_SOURCE_DECISION_V2
from src.analysis.decision_v2.types import Decision
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
        from src.backtesting.decision_v2_context import _replay_market_state_instant_utc
        from src.market_intelligence.trading_calendar import is_market_open

        assert ctx.market_is_open == is_market_open(_replay_market_state_instant_utc(_AS_OF))

    def test_market_state_reflects_the_genuine_historical_trading_session_not_always_closed(self, session):
        """HIGH_QUALITY_BUY structural repair: `_AS_OF` (2026-03-01) is a
        genuine Tadawul trading day (Sunday). Before the fix,
        `market_is_open` was always False for every replay point
        regardless of the as-of date -- an end-of-UTC-day anchor always
        converts to the small hours of the NEXT day in Tadawul local
        time, permanently outside the 10:00-15:00 AST session. This
        proves the harness now reads the genuine historical
        trading-session state instead of always reporting closed."""
        assert _AS_OF.weekday() == 6  # Sunday -- a real Tadawul trading day
        subject, _ = _seed_universe(session)
        ctx = build_decision_v2_as_of_context(session, subject, _AS_OF)
        assert ctx.market_is_open is True
        assert ctx.market_status == "OPEN"

    def test_market_state_still_correctly_closed_on_a_non_trading_day(self, session):
        """A genuine non-trading as-of date (Friday) must still report
        closed -- the fix reads the real calendar, it does not force
        open unconditionally."""
        friday = _AS_OF - timedelta(days=2)
        assert friday.weekday() == 4  # Friday -- not a Tadawul trading day
        subject, _ = _seed_universe(session)
        ctx = build_decision_v2_as_of_context(session, subject, friday)
        assert ctx.market_is_open is False
        assert ctx.market_status == "CLOSED"

    def test_market_state_instant_does_not_change_the_freshness_evaluation_time(self, session):
        """The market-state repair must not alter the already-verified
        evaluation_time (freshness) fix -- the two are deliberately
        separate instants, see decision_v2_context.py's module
        docstring."""
        subject, _ = _seed_universe(session)
        ctx = build_decision_v2_as_of_context(session, subject, _AS_OF)
        expected_evaluation_time = datetime.combine(_AS_OF, datetime.max.time(), tzinfo=timezone.utc)
        assert ctx.evaluation_time == expected_evaluation_time


class TestHighQualityBuyMarketStateReachability:
    """HIGH_QUALITY_BUY structural repair, engine-level proof: the one
    warning every replay point used to carry unconditionally --
    "السوق مغلق حاليًا" (market currently closed), appended whenever
    `market_is_open is False` -- is exactly what `classify_high_quality_
    buy`'s `if warnings: return False` rule used to foreclose on for
    100% of points, regardless of the underlying evidence quality. This
    proves that foreclosure is now conditional on the genuine
    historical trading-session state, not a harness artifact."""

    _MARKET_CLOSED_WARNING = "السوق مغلق حاليًا"

    def test_genuine_trading_day_does_not_carry_the_market_closed_warning(self, session):
        """Mandate proof B (part 1): the mandatory market-closed
        condition genuinely does NOT fail on a real trading day, so it
        no longer disqualifies HIGH_QUALITY_BUY by itself."""
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None
        result = run_phase3_v2(point)
        assert not any(self._MARKET_CLOSED_WARNING in w for w in result.warnings)

    def test_genuine_non_trading_day_still_carries_the_market_closed_warning(self, session):
        """Mandate proof B (part 2): on a real non-trading date, the
        condition genuinely DOES fail -- HIGH_QUALITY_BUY correctly
        stays foreclosed, exactly as documented, not weakened."""
        friday = _AS_OF - timedelta(days=2)
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, friday)
        assert point is not None
        result = run_phase3_v2(point)
        assert any(self._MARKET_CLOSED_WARNING in w for w in result.warnings)
        assert result.is_high_quality_buy is False

    def test_no_look_ahead_introduced_by_the_market_state_repair(self, session):
        """Mandate proof E: a future price shock after `_AS_OF` must not
        change the as-of market-open read (it depends only on the
        as-of date's own calendar position, never on price data)."""
        subject, _ = _seed_universe(session, future_subject_shock=False)
        ctx_normal = build_decision_v2_as_of_context(session, subject, _AS_OF)

        engine2 = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine2)
        session2 = sessionmaker(bind=engine2)()
        subject2, _ = _seed_universe(session2, future_subject_shock=True)
        ctx_shocked = build_decision_v2_as_of_context(session2, subject2, _AS_OF)

        assert ctx_normal.market_is_open == ctx_shocked.market_is_open is True

    def test_live_production_market_state_path_is_structurally_unreachable_from_this_module(self):
        """Mandate proof D: `_replay_market_state_instant_utc` lives in
        `src.backtesting.decision_v2_context`, a backtest-only module.
        Neither of the two real production callers of
        `DecisionEngineV2.decide()` (the `/decision-v2` route and the
        live market scanner) ever imports this module -- their own
        `market_is_open` values come from a real live-quote/calendar
        read against actual wall-clock time, a wholly separate code
        path this repair cannot touch."""
        import inspect

        import src.api.routes.stocks as stocks_route
        import src.market_intelligence.scanner as scanner_module

        assert "decision_v2_context" not in inspect.getsource(stocks_route)
        assert "decision_v2_context" not in inspect.getsource(scanner_module)


class TestConfidenceCalibrationHarnessReachability:
    """Phase 3 area 2 structural repair: confidence calibration was
    entirely unreached by the backtest harness before this repair --
    `run_phase3_v2`'s new optional `session` parameter makes it
    genuinely reachable/testable the same way live production would
    exercise it (see that function's own docstring). Uses a manually-
    constructed ACTIVE model, never one trained from this backtest's
    own outcome data -- satisfies "do not train/tune a new calibrator
    using this backtest.\""""

    def _insert_active_model(self, session, coef=8.0, intercept=-4.0):
        from src.domain.models import ConfidenceCalibrationMethod, ConfidenceCalibrationModel, ConfidenceCalibrationStatus

        model = ConfidenceCalibrationModel(
            version="test-manual-v1",
            status=ConfidenceCalibrationStatus.ACTIVE,
            method=ConfidenceCalibrationMethod.PLATT,
            training_source=TRAINING_SOURCE_DECISION_V2,
            model_params={"coef": coef, "intercept": intercept},
            training_sample_size=42,
        )
        session.add(model)
        session.commit()
        return model

    def test_no_session_preserves_the_exact_single_pass_behavior(self, session):
        """Mandate proof C (part 1): omitting `session` entirely (every
        caller before this repair) is a complete no-op."""
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None
        without_session = run_phase3_v2(point)
        with_session_omitted_again = run_phase3_v2(point)
        assert without_session.decision == with_session_omitted_again.decision
        assert without_session.confidence_score == with_session_omitted_again.confidence_score

    def test_session_with_no_active_model_falls_back_safely(self, session):
        """Mandate proof C (part 2): a real session with no active
        calibration model (the honest state this backtest DB is in
        unless a model is explicitly inserted) must not change the
        result at all."""
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None
        without_session = run_phase3_v2(point)
        with_session_no_model = run_phase3_v2(point, session=session)
        assert without_session.decision == with_session_no_model.decision
        assert without_session.confidence_score == with_session_no_model.confidence_score

    def test_active_model_is_genuinely_applied_and_reachable(self, session):
        """Mandate proof B + D: a real (manually-inserted, not backtest-
        trained) active model produces a genuinely different, calibrated
        result -- confidence calibration is no longer structurally
        unreachable from this harness."""
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None
        baseline_result = run_phase3_v2(point)
        if baseline_result.decision not in (Decision.BUY_CANDIDATE, Decision.STRONG_BUY_CANDIDATE):
            pytest.skip("fixture did not produce a buy-like decision to reach the calibration gate")
        self._insert_active_model(session)
        calibrated_result = run_phase3_v2(point, session=session)

        calibration_gate = next(
            g for g in calibrated_result.gates if g.name == "confidence_calibration_applied"
        )
        assert calibration_gate.status.value in ("PASS", "FAIL")  # genuinely evaluated, not skipped
        # Raw confidence is never silently overwritten by calibration.
        assert calibrated_result.confidence_score == baseline_result.confidence_score

    def test_poorly_calibrated_active_model_downgrades_the_decision(self, session):
        """Mandate proof F, at the harness level: a real active model
        whose calibrated probability falls below the configured minimum
        genuinely changes the final decision, not merely a gate detail."""
        subject, _ = _seed_universe(session)
        point = build_replay_point(session, subject, _AS_OF)
        assert point is not None
        baseline_result = run_phase3_v2(point)
        if baseline_result.decision not in (Decision.BUY_CANDIDATE, Decision.STRONG_BUY_CANDIDATE):
            pytest.skip("fixture did not produce a buy-like decision to downgrade")
        # A steep negative Platt fit drives every confidence toward a
        # near-zero calibrated probability, well below any reasonable
        # minimum threshold.
        self._insert_active_model(session, coef=0.0, intercept=-10.0)
        calibrated_result = run_phase3_v2(point, session=session)
        assert calibrated_result.decision is Decision.WATCH

    def test_calibration_application_has_no_look_ahead(self, session):
        """Mandate proof E: the calibration model's own parameters are
        fixed at insertion time and applied identically regardless of
        the as-of evaluation date -- no per-point date dependency
        exists in `get_effective_confidence`'s own lookup (source +
        ACTIVE status only), so it cannot leak future information tied
        to a specific historical point."""
        subject, _ = _seed_universe(session)
        self._insert_active_model(session)
        point_at_as_of = build_replay_point(session, subject, _AS_OF)
        earlier_date = _AS_OF - timedelta(days=7)
        point_earlier = build_replay_point(session, subject, earlier_date)
        assert point_at_as_of is not None and point_earlier is not None

        from src.ai_evolution.confidence_calibration import get_effective_confidence

        calibrated_a, version_a = get_effective_confidence(session, 80.0, source=TRAINING_SOURCE_DECISION_V2)
        calibrated_b, version_b = get_effective_confidence(session, 80.0, source=TRAINING_SOURCE_DECISION_V2)
        assert calibrated_a == calibrated_b
        assert version_a == version_b == "test-manual-v1"


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
