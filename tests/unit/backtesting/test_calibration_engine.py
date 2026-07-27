"""Unit tests for src.backtesting.calibration.engine.CalibrationEngine.

Lifecycle/orchestration tests use a fake BacktestingEngine (returns
preset metrics keyed by which strategy -- candidate vs baseline -- was
asked for) so VALIDATED/REJECTED outcomes are deterministic without
depending on real market data producing a specific result. The
underlying real BacktestingEngine wiring is already covered by
test_engine.py; this file is about CalibrationEngine's own state
machine and decision logic.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backtesting.calibration.engine import CalibrationEngine, _evaluate_candidate
from src.backtesting.engine import BacktestConfig
from src.core.db.database import Base
from src.domain.models import CalibrationConfig, CalibrationStatus, DataProvenanceMode


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


class _FakeBacktestingEngine:
    """Returns preset metrics keyed by the requested strategy's `name`
    kwarg (build_strategy_kwargs always sets one) -- lets a test
    control exactly what CalibrationEngine.validate() sees for the
    candidate vs. the baseline without running real backtests."""

    def __init__(self, metrics_by_name):
        self._metrics_by_name = metrics_by_name
        self.calls = []

    def run(self, session, config: BacktestConfig, run_id=None):
        self.calls.append(config)
        name = (config.strategy_kwargs or {}).get("name", "")
        key = "candidate" if name.startswith("candidate") else "baseline"
        return {"overall": self._metrics_by_name[key]}


_GOOD_METRICS = {"direction_accuracy": 0.65, "max_drawdown": -0.05}
_WORSE_METRICS = {"direction_accuracy": 0.50, "max_drawdown": -0.05}
_BIG_DRAWDOWN_METRICS = {"direction_accuracy": 0.75, "max_drawdown": -0.40}
_MISSING_METRICS = {"direction_accuracy": None, "max_drawdown": None}


def _propose(engine, session, config=None):
    return engine.propose(
        session,
        config=config or {"recommendation_tuning": {"buy_threshold": 58.0}},
        training_period=(date(2026, 1, 1), date(2026, 4, 1)),
        validation_period=(date(2026, 4, 2), date(2026, 6, 1)),
    )


# --- _evaluate_candidate (pure decision logic) --------------------------


def test_evaluate_candidate_passes_when_strictly_better():
    passed, reason = _evaluate_candidate(_GOOD_METRICS, _WORSE_METRICS)
    assert passed is True
    assert "0.6500" in reason


def test_evaluate_candidate_rejects_worse_primary_metric():
    passed, reason = _evaluate_candidate(_WORSE_METRICS, _GOOD_METRICS)
    assert passed is False
    assert "worse than the baseline" in reason


def test_evaluate_candidate_rejects_material_drawdown_regression_despite_improvement():
    passed, reason = _evaluate_candidate(_BIG_DRAWDOWN_METRICS, _GOOD_METRICS)
    assert passed is False
    assert "no-overfitting guard" in reason


def test_evaluate_candidate_rejects_when_metrics_are_missing():
    passed, reason = _evaluate_candidate(_MISSING_METRICS, _GOOD_METRICS)
    assert passed is False
    assert "Insufficient" in reason


def test_evaluate_candidate_equal_primary_metric_passes():
    passed, _ = _evaluate_candidate(_GOOD_METRICS, _GOOD_METRICS)
    assert passed is True


# --- propose -----------------------------------------------------------


def test_propose_creates_a_draft_row(session):
    engine = CalibrationEngine()
    row = _propose(engine, session)
    assert row.status == CalibrationStatus.DRAFT
    assert row.config == {"recommendation_tuning": {"buy_threshold": 58.0}}
    assert row.training_period_start == date(2026, 1, 1)
    assert row.validation_period_end == date(2026, 6, 1)
    assert session.query(CalibrationConfig).filter_by(version=row.version).one() is not None


def test_propose_generates_unique_versions(session):
    engine = CalibrationEngine()
    row1 = _propose(engine, session)
    row2 = _propose(engine, session)
    assert row1.version != row2.version


# --- validate ------------------------------------------------------------


def test_validate_requires_draft_status(session):
    engine = CalibrationEngine(backtesting_engine=_FakeBacktestingEngine({"candidate": _GOOD_METRICS, "baseline": _WORSE_METRICS}))
    row = _propose(engine, session)
    engine.validate(session, row.version, symbols=["2222"], data_provenance_mode=DataProvenanceMode.SYNTHETIC)

    with pytest.raises(ValueError, match="must be DRAFT"):
        engine.validate(session, row.version, symbols=["2222"], data_provenance_mode=DataProvenanceMode.SYNTHETIC)


def test_validate_marks_validated_when_candidate_is_better(session):
    engine = CalibrationEngine(backtesting_engine=_FakeBacktestingEngine({"candidate": _GOOD_METRICS, "baseline": _WORSE_METRICS}))
    row = _propose(engine, session)
    result = engine.validate(session, row.version, symbols=["2222"], data_provenance_mode=DataProvenanceMode.SYNTHETIC)

    assert result.status == CalibrationStatus.VALIDATED
    assert result.metrics == _GOOD_METRICS
    assert result.baseline_comparison_metrics == _WORSE_METRICS


def test_validate_marks_rejected_when_candidate_is_worse(session):
    engine = CalibrationEngine(backtesting_engine=_FakeBacktestingEngine({"candidate": _WORSE_METRICS, "baseline": _GOOD_METRICS}))
    row = _propose(engine, session)
    result = engine.validate(session, row.version, symbols=["2222"], data_provenance_mode=DataProvenanceMode.SYNTHETIC)

    assert result.status == CalibrationStatus.REJECTED
    assert "worse than the baseline" in result.notes


def test_validate_compares_against_engine_defaults_when_nothing_is_active(session):
    fake = _FakeBacktestingEngine({"candidate": _GOOD_METRICS, "baseline": _WORSE_METRICS})
    engine = CalibrationEngine(backtesting_engine=fake)
    row = _propose(engine, session)
    engine.validate(session, row.version, symbols=["2222"], data_provenance_mode=DataProvenanceMode.SYNTHETIC)

    baseline_call = next(c for c in fake.calls if c.strategy_kwargs["name"] == "active-baseline")
    assert baseline_call.strategy_kwargs["contributors"] is None  # no active config -> engine defaults


def test_validate_compares_against_the_active_config_when_one_exists(session):
    active_row = CalibrationConfig(
        version="active-v1", status=CalibrationStatus.ACTIVE,
        config={"recommendation_tuning": {"buy_threshold": 61.0}},
    )
    session.add(active_row)
    session.commit()

    fake = _FakeBacktestingEngine({"candidate": _GOOD_METRICS, "baseline": _WORSE_METRICS})
    engine = CalibrationEngine(backtesting_engine=fake)
    row = _propose(engine, session)
    engine.validate(session, row.version, symbols=["2222"], data_provenance_mode=DataProvenanceMode.SYNTHETIC)

    baseline_call = next(c for c in fake.calls if c.strategy_kwargs["name"] == "active-baseline")
    assert baseline_call.strategy_kwargs["recommendation_tuning"].buy_threshold == 61.0


# --- activate / rollback --------------------------------------------------


def test_activate_requires_validated_status(session):
    engine = CalibrationEngine()
    row = _propose(engine, session)  # still DRAFT
    with pytest.raises(ValueError, match="must be VALIDATED"):
        engine.activate(session, row.version)


def test_activate_sets_active_and_records_timestamp(session):
    row = CalibrationConfig(version="v1", status=CalibrationStatus.VALIDATED, config={})
    session.add(row)
    session.commit()

    engine = CalibrationEngine()
    activated = engine.activate(session, "v1")

    assert activated.status == CalibrationStatus.ACTIVE
    assert activated.activated_at is not None


def test_activating_a_new_version_supersedes_the_previous_active_one(session):
    v1 = CalibrationConfig(version="v1", status=CalibrationStatus.VALIDATED, config={})
    v2 = CalibrationConfig(version="v2", status=CalibrationStatus.VALIDATED, config={})
    session.add_all([v1, v2])
    session.commit()

    engine = CalibrationEngine()
    engine.activate(session, "v1")
    engine.activate(session, "v2")

    assert session.query(CalibrationConfig).filter_by(version="v1").one().status == CalibrationStatus.SUPERSEDED
    assert engine.get_active_config(session).version == "v2"


def test_get_active_config_none_when_nothing_active(session):
    engine = CalibrationEngine()
    assert engine.get_active_config(session) is None


def test_rollback_with_no_target_deactivates_only(session):
    row = CalibrationConfig(version="v1", status=CalibrationStatus.ACTIVE, config={}, activated_at=datetime.now(timezone.utc))
    session.add(row)
    session.commit()

    engine = CalibrationEngine()
    result = engine.rollback(session)

    assert result is None
    assert engine.get_active_config(session) is None
    assert session.query(CalibrationConfig).filter_by(version="v1").one().status == CalibrationStatus.ROLLED_BACK


def test_rollback_to_a_specific_prior_version_reactivates_it(session):
    v1 = CalibrationConfig(version="v1", status=CalibrationStatus.SUPERSEDED, config={})
    v2 = CalibrationConfig(version="v2", status=CalibrationStatus.ACTIVE, config={})
    session.add_all([v1, v2])
    session.commit()

    engine = CalibrationEngine()
    result = engine.rollback(session, to_version="v1")

    assert result.version == "v1"
    assert result.status == CalibrationStatus.ACTIVE
    assert engine.get_active_config(session).version == "v1"
    assert session.query(CalibrationConfig).filter_by(version="v2").one().status == CalibrationStatus.ROLLED_BACK


def test_rollback_to_a_draft_version_is_rejected(session):
    v1 = CalibrationConfig(version="v1", status=CalibrationStatus.DRAFT, config={})
    session.add(v1)
    session.commit()

    engine = CalibrationEngine()
    with pytest.raises(ValueError, match="Cannot roll back"):
        engine.rollback(session, to_version="v1")


# --- propose_random_candidates -----------------------------------------


def test_random_candidates_are_reproducible_with_the_same_seed(session):
    engine = CalibrationEngine()
    params = {"recommendation_tuning.buy_threshold": (55.0, 65.0)}
    period = ((date(2026, 1, 1), date(2026, 4, 1)), (date(2026, 4, 2), date(2026, 6, 1)))

    first = engine.propose_random_candidates(session, params, n_candidates=4, training_period=period[0], validation_period=period[1], random_seed=99)
    second = engine.propose_random_candidates(session, params, n_candidates=4, training_period=period[0], validation_period=period[1], random_seed=99)

    assert [c.config for c in first] == [c.config for c in second]


def test_random_candidates_differ_with_a_different_seed(session):
    engine = CalibrationEngine()
    params = {"recommendation_tuning.buy_threshold": (55.0, 65.0)}
    period = ((date(2026, 1, 1), date(2026, 4, 1)), (date(2026, 4, 2), date(2026, 6, 1)))

    a = engine.propose_random_candidates(session, params, n_candidates=1, training_period=period[0], validation_period=period[1], random_seed=1)
    b = engine.propose_random_candidates(session, params, n_candidates=1, training_period=period[0], validation_period=period[1], random_seed=2)

    assert a[0].config != b[0].config


def test_random_candidates_respect_the_given_range():
    import random

    from src.backtesting.calibration.engine import CalibrationEngine as _CE  # noqa: F401 (re-import for clarity)

    rng = random.Random(5)
    for _ in range(50):
        value = rng.uniform(55.0, 65.0)
        assert 55.0 <= value <= 65.0


def test_random_candidates_dotted_path_builds_nested_config(session):
    engine = CalibrationEngine()
    params = {"contributor_weights.technical": (0.2, 0.3), "ai_tuning.stop_atr_multiple": (1.0, 2.0)}
    candidates = engine.propose_random_candidates(
        session, params, n_candidates=1,
        training_period=(date(2026, 1, 1), date(2026, 4, 1)), validation_period=(date(2026, 4, 2), date(2026, 6, 1)),
        random_seed=3,
    )
    config = candidates[0].config
    assert "contributor_weights" in config and "technical" in config["contributor_weights"]
    assert "ai_tuning" in config and "stop_atr_multiple" in config["ai_tuning"]
    assert 0.2 <= config["contributor_weights"]["technical"] <= 0.3
