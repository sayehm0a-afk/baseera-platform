"""CalibrationEngine: proposes, validates, activates, and rolls back
AIDecisionEngine/RecommendationEngine tuning configurations -- Phase
5's calibration lifecycle.

Every step is explicit and durable (CalibrationConfig rows), never
silent:
  - `propose()` only ever creates a DRAFT row -- it never touches
    production behavior.
  - `validate()` runs the candidate *and* the currently-active
    configuration (or engine defaults, if none is active) through
    BacktestingEngine over the identical validation period, so
    "is this better" is always a same-period, like-for-like
    comparison -- never a claim measured against a different window.
    A candidate is only marked VALIDATED if it does not regress the
    primary metric and does not materially worsen drawdown (the
    anti-overfitting guard); otherwise it is marked REJECTED with the
    reason recorded in `notes`.
  - `activate()` requires VALIDATED status and is the only path that
    changes which configuration is "active" -- at most one row is
    ACTIVE at a time (enforced here, not by a DB constraint; see
    CalibrationConfig's own docstring for why).
  - `rollback()` deactivates the current ACTIVE config and, if asked,
    reactivates a specific prior version -- always an explicit call,
    never automatic.

Wiring an ACTIVE calibration into the *live* /recommendation and
/decision routes is intentionally not done in this milestone --
disclosed in docs/BACKTESTING_AND_CALIBRATION.md -- this module only
builds the infrastructure to propose/validate/activate/roll back a
configuration and prove the lifecycle works end to end.
"""

import uuid
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.backtesting.calibration.parameters import build_strategy_kwargs
from src.backtesting.engine import BacktestConfig, BacktestingEngine
from src.domain.models import CalibrationConfig, CalibrationStatus, DataProvenanceMode

# The metric a candidate must not regress on to be validated -- direction
# accuracy is the most fundamental, least gameable headline number (unlike
# e.g. average_forward_return, which a single lucky outlier can dominate).
_PRIMARY_METRIC = "direction_accuracy"
# A candidate may not have a materially worse (more negative) max_drawdown
# than the baseline even if the primary metric improved -- this is the
# concrete "reject a candidate that improves one metric while materially
# worsening risk or drawdown" guard.
_MAX_DRAWDOWN_REGRESSION_TOLERANCE = 0.05


def _generate_version() -> str:
    return f"cal-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _evaluate_candidate(candidate_metrics: Dict, baseline_metrics: Dict) -> Tuple[bool, str]:
    candidate_primary = candidate_metrics.get(_PRIMARY_METRIC)
    baseline_primary = baseline_metrics.get(_PRIMARY_METRIC)
    if candidate_primary is None or baseline_primary is None:
        return False, (
            f"Insufficient validation-period data to compute {_PRIMARY_METRIC} for the candidate "
            "and/or baseline -- cannot honestly compare, so the candidate is not validated."
        )

    if candidate_primary < baseline_primary:
        return False, (
            f"Candidate {_PRIMARY_METRIC} ({candidate_primary:.4f}) is worse than the baseline "
            f"({baseline_primary:.4f}) on the validation period."
        )

    candidate_dd = candidate_metrics.get("max_drawdown")
    baseline_dd = baseline_metrics.get("max_drawdown")
    if candidate_dd is not None and baseline_dd is not None and candidate_dd < baseline_dd - _MAX_DRAWDOWN_REGRESSION_TOLERANCE:
        return False, (
            f"Candidate {_PRIMARY_METRIC} improved ({candidate_primary:.4f} vs {baseline_primary:.4f}) but "
            f"max_drawdown is materially worse ({candidate_dd:.4f} vs {baseline_dd:.4f}) -- rejected by the "
            "no-overfitting guard rather than accepted for a one-metric gain."
        )

    return True, (
        f"Candidate {_PRIMARY_METRIC} ({candidate_primary:.4f}) >= baseline ({baseline_primary:.4f}) with no "
        "material max_drawdown regression."
    )


class CalibrationEngine:
    def __init__(self, backtesting_engine: Optional[BacktestingEngine] = None):
        self._backtesting_engine = backtesting_engine or BacktestingEngine()

    def get_active_config(self, session: Session) -> Optional[CalibrationConfig]:
        return session.query(CalibrationConfig).filter_by(status=CalibrationStatus.ACTIVE).one_or_none()

    def propose(
        self,
        session: Session,
        config: Dict,
        training_period: Tuple[date, date],
        validation_period: Tuple[date, date],
        notes: Optional[str] = None,
        random_seed: Optional[int] = None,
    ) -> CalibrationConfig:
        row = CalibrationConfig(
            version=_generate_version(),
            status=CalibrationStatus.DRAFT,
            config=config,
            training_period_start=training_period[0],
            training_period_end=training_period[1],
            validation_period_start=validation_period[0],
            validation_period_end=validation_period[1],
            random_seed=random_seed,
            notes=notes,
        )
        session.add(row)
        session.commit()
        return row

    def propose_random_candidates(
        self,
        session: Session,
        param_ranges: Dict[str, Tuple[float, float]],
        n_candidates: int,
        training_period: Tuple[date, date],
        validation_period: Tuple[date, date],
        random_seed: int,
    ) -> List[CalibrationConfig]:
        """Samples `n_candidates` configurations uniformly from
        `param_ranges` (dotted paths, e.g. "recommendation_tuning.buy_threshold":
        (55.0, 65.0), "contributor_weights.technical": (0.2, 0.35)) using a
        seeded, local `random.Random` -- the same seed always produces
        the same candidates, satisfying Phase 4's reproducibility
        requirement without relying on (and never touching) the
        global `random` module state.
        """
        import random

        rng = random.Random(random_seed)
        candidates = []
        for _ in range(n_candidates):
            config: Dict = {}
            for dotted_path, (low, high) in param_ranges.items():
                category, field = dotted_path.split(".", 1)
                config.setdefault(category, {})[field] = rng.uniform(low, high)
            candidates.append(
                self.propose(
                    session, config, training_period, validation_period,
                    notes=f"Randomly sampled (seed={random_seed}).", random_seed=random_seed,
                )
            )
        return candidates

    def validate(
        self,
        session: Session,
        version: str,
        symbols: List[str],
        data_provenance_mode: DataProvenanceMode,
        **backtest_kwargs,
    ) -> CalibrationConfig:
        row = session.query(CalibrationConfig).filter_by(version=version).one()
        if row.status != CalibrationStatus.DRAFT:
            raise ValueError(f"Calibration {version!r} must be DRAFT to validate (currently {row.status}).")

        candidate_kwargs = build_strategy_kwargs(row.config, name=f"candidate-{version}")
        active_row = self.get_active_config(session)
        baseline_kwargs = build_strategy_kwargs(active_row.config if active_row else {}, name="active-baseline")

        base_config = BacktestConfig(
            symbols=symbols,
            start_date=row.validation_period_start,
            end_date=row.validation_period_end,
            data_provenance_mode=data_provenance_mode,
            strategy="ai_decision_engine",
            **backtest_kwargs,
        )
        candidate_report = self._backtesting_engine.run(
            session, replace(base_config, strategy_kwargs=candidate_kwargs), run_id=row.validation_run_id
        )
        baseline_report = self._backtesting_engine.run(
            session, replace(base_config, strategy_kwargs=baseline_kwargs), run_id=None
        )

        row.metrics = candidate_report["overall"]
        row.baseline_comparison_metrics = baseline_report["overall"]

        passed, reason = _evaluate_candidate(candidate_report["overall"], baseline_report["overall"])
        row.status = CalibrationStatus.VALIDATED if passed else CalibrationStatus.REJECTED
        row.notes = f"{row.notes}\n{reason}" if row.notes else reason
        session.commit()
        return row

    def activate(self, session: Session, version: str) -> CalibrationConfig:
        row = session.query(CalibrationConfig).filter_by(version=version).one()
        if row.status != CalibrationStatus.VALIDATED:
            raise ValueError(f"Calibration {version!r} must be VALIDATED to activate (currently {row.status}).")

        current_active = self.get_active_config(session)
        if current_active is not None:
            current_active.status = CalibrationStatus.SUPERSEDED
            current_active.deactivated_at = datetime.now(timezone.utc)

        row.status = CalibrationStatus.ACTIVE
        row.activated_at = datetime.now(timezone.utc)
        session.commit()
        return row

    def rollback(self, session: Session, to_version: Optional[str] = None) -> Optional[CalibrationConfig]:
        current_active = self.get_active_config(session)
        if current_active is not None:
            current_active.status = CalibrationStatus.ROLLED_BACK
            current_active.deactivated_at = datetime.now(timezone.utc)

        if to_version is None:
            session.commit()
            return None  # no config active -> AIDecisionEngine/RecommendationEngine fall back to their own defaults

        target = session.query(CalibrationConfig).filter_by(version=to_version).one()
        if target.status not in (CalibrationStatus.SUPERSEDED, CalibrationStatus.ROLLED_BACK, CalibrationStatus.VALIDATED):
            raise ValueError(f"Cannot roll back to {to_version!r} (status {target.status}).")

        target.status = CalibrationStatus.ACTIVE
        target.activated_at = datetime.now(timezone.utc)
        session.commit()
        return target
