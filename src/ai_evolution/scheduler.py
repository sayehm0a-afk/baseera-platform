"""Recurring, unattended AI Evolution Layer background jobs -- the
same "one asyncio.Task, run then sleep(interval), never overlap
itself" design `src.market_intelligence.scheduler
.IntervalMarketIntelligenceScheduler` already established, applied to
`src.ai_evolution.outcome_evaluation.evaluate_due_outcomes` (E2) and
`src.ai_evolution.pattern_discovery.discover_patterns` (E5) instead of
a market scan.

Both disabled by default (`OUTCOME_EVALUATION_SCHEDULER_ENABLED`/
`PATTERN_DISCOVERY_SCHEDULER_ENABLED=false`) -- the same secure/
inert-by-default posture every other scheduler in this codebase
already uses.
"""

import asyncio
import contextlib
import logging
from typing import Callable, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from src.ai_evolution.config import (
    get_daily_intelligence_aggregation_interval_seconds,
    get_daily_reflection_interval_seconds,
    get_decision_v2_outcome_interval_seconds,
    get_decision_v2_outcome_leader_heartbeat_seconds,
    get_decision_v2_outcome_leader_lease_seconds,
    get_outcome_evaluation_interval_seconds,
    get_pattern_discovery_interval_seconds,
)
from src.ai_evolution.daily_intelligence_aggregation import aggregate_daily_intelligence
from src.ai_evolution.daily_reflection import generate_daily_reflection
from src.ai_evolution.decision_v2_outcome_evaluation import evaluate_pending_outcomes
from src.ai_evolution.outcome_evaluation import evaluate_due_outcomes
from src.ai_evolution.pattern_discovery import discover_patterns
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock

logger = logging.getLogger(__name__)


@runtime_checkable
class IOutcomeEvaluationScheduler(Protocol):
    def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    @property
    def is_running(self) -> bool:
        ...


class OutcomeEvaluationScheduler:
    """The one concrete `IOutcomeEvaluationScheduler` this codebase
    ships. `interval_seconds` defaults to
    `OUTCOME_EVALUATION_INTERVAL_SECONDS` -- passing one explicitly
    overrides the environment for this instance."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        interval_seconds: Optional[int] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_outcome_evaluation_interval_seconds()
        )
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self._task is not None:
            logger.warning("OutcomeEvaluationScheduler.start() called while already running -- ignoring.")
            return
        self._task = asyncio.ensure_future(self._loop())
        logger.info("OutcomeEvaluationScheduler started (interval_seconds=%s).", self._interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("OutcomeEvaluationScheduler stopped.")

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_one_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                # evaluate_due_outcomes only raises on a genuine DB/session
                # failure (per-row errors would be a bug, not handled here) --
                # logged, not raised, so the loop keeps running on schedule.
                logger.exception("Unexpected error evaluating due recommendation outcomes.")
            await asyncio.sleep(self._interval_seconds)

    async def _run_one_cycle(self) -> None:
        session = self._session_factory()
        try:
            summary = await asyncio.to_thread(evaluate_due_outcomes, session)
            logger.info(
                "Outcome evaluation cycle: %d evaluated, %d expired (no data), %d still pending.",
                summary.evaluated,
                summary.expired_no_data,
                summary.skipped_pending,
            )
        finally:
            session.close()


class PatternDiscoveryScheduler:
    """Weekly (by default) re-run of `discover_patterns()` -- same
    shape as `OutcomeEvaluationScheduler` above."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        interval_seconds: Optional[int] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_pattern_discovery_interval_seconds()
        )
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self._task is not None:
            logger.warning("PatternDiscoveryScheduler.start() called while already running -- ignoring.")
            return
        self._task = asyncio.ensure_future(self._loop())
        logger.info("PatternDiscoveryScheduler started (interval_seconds=%s).", self._interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("PatternDiscoveryScheduler stopped.")

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_one_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error discovering patterns.")
            await asyncio.sleep(self._interval_seconds)

    async def _run_one_cycle(self) -> None:
        session = self._session_factory()
        try:
            patterns = await asyncio.to_thread(discover_patterns, session)
            logger.info("Pattern discovery cycle: %d patterns discovered/re-validated.", len(patterns))
        finally:
            session.close()


class DailyReflectionScheduler:
    """Daily (by default) re-run of `generate_daily_reflection()` --
    same shape as `OutcomeEvaluationScheduler`/`PatternDiscoveryScheduler`
    above."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        interval_seconds: Optional[int] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_daily_reflection_interval_seconds()
        )
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self._task is not None:
            logger.warning("DailyReflectionScheduler.start() called while already running -- ignoring.")
            return
        self._task = asyncio.ensure_future(self._loop())
        logger.info("DailyReflectionScheduler started (interval_seconds=%s).", self._interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("DailyReflectionScheduler stopped.")

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_one_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error generating the daily reflection report.")
            await asyncio.sleep(self._interval_seconds)

    async def _run_one_cycle(self) -> None:
        session = self._session_factory()
        try:
            report = await asyncio.to_thread(generate_daily_reflection, session)
            logger.info(
                "Daily reflection cycle: %d recommendation(s) reviewed for %s.",
                report.recommendations_reviewed,
                report.review_date,
            )
        finally:
            session.close()


class DailyIntelligenceAggregationScheduler:
    """Daily (by default) re-run of `aggregate_daily_intelligence()` --
    same shape as the other schedulers above. E9 (Part 12 of the
    design): pre-aggregates so the staff-only Intelligence Dashboard
    reads a precomputed row instead of live-computing on every load."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        interval_seconds: Optional[int] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_daily_intelligence_aggregation_interval_seconds()
        )
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self._task is not None:
            logger.warning("DailyIntelligenceAggregationScheduler.start() called while already running -- ignoring.")
            return
        self._task = asyncio.ensure_future(self._loop())
        logger.info("DailyIntelligenceAggregationScheduler started (interval_seconds=%s).", self._interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("DailyIntelligenceAggregationScheduler stopped.")

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_one_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error aggregating daily AI Evolution Layer intelligence.")
            await asyncio.sleep(self._interval_seconds)

    async def _run_one_cycle(self) -> None:
        session = self._session_factory()
        try:
            snapshot = await asyncio.to_thread(aggregate_daily_intelligence, session)
            logger.info(
                "Daily intelligence aggregation cycle: %d recommendation(s) aggregated for %s.",
                snapshot.recommendations_evaluated,
                snapshot.snapshot_date,
            )
        finally:
            session.close()


_DECISION_V2_OUTCOME_LEASE_KEY = "basirah:decision_v2_outcome_scheduler:leader"


class DecisionV2OutcomeScheduler:
    """M10: recurring re-run of `evaluate_pending_outcomes()` -- same
    shape as `OutcomeEvaluationScheduler` above, but for
    `DecisionV2Outcome` rows instead of the older
    `RecommendationOutcome` rows. Read-only against already-ingested
    price data (no SAHMK call), so running it never touches quota
    regardless of interval.

    2026-08-18 production evidence: `main.py`'s
    `@app.on_event("startup")` runs independently in every one of
    Gunicorn's worker processes (Dockerfile: `--workers 4`), so
    `start()` ran four times, each driving its own full, redundant
    evaluation cycle at the identical wall-clock offset every 3600s --
    logs showed four near-simultaneous "DecisionV2Outcome evaluation
    cycle:" lines per interval instead of one. Harmless to correctness
    (evaluate_pending_outcomes is idempotent and the DB-level unique
    constraint on decision_v2_outcomes.decision_v2_snapshot_id prevents
    any duplicate row), but wasteful. `IngestionScheduler` closed the
    identical multi-worker duplication incident for its own four job
    loops via a Redis-backed `SchedulerLeaderLock`
    (scheduler_leader_lock.py); `_leader_lock` here (a third,
    independent `SchedulerLeaderLock` instance/lease key) applies the
    same fix: a dedicated, fast heartbeat task -- deliberately
    independent of this scheduler's own long (3600s default) cycle
    interval, so a crashed leader's lease still expires and fails over
    within roughly one heartbeat, not up to a full cycle later --
    keeps `self._is_leader` current, and the cycle loop skips its own
    tick's work entirely (zero DB writes, zero log line) whenever this
    worker does not currently hold the lease."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        interval_seconds: Optional[int] = None,
        leader_lock: Optional[SchedulerLeaderLock] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_decision_v2_outcome_interval_seconds()
        )
        self._leader_lock = leader_lock or SchedulerLeaderLock(lease_key=_DECISION_V2_OUTCOME_LEASE_KEY)
        self._task: Optional[asyncio.Task] = None
        self._leadership_task: Optional[asyncio.Task] = None
        self._is_leader: bool = False
        self._skipped_due_to_not_leader_count: int = 0

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    @property
    def is_leader(self) -> bool:
        """Whether THIS process currently holds the
        decision-v2-outcome-scheduler lease -- real, current state (the
        heartbeat task renews/re-checks it every
        `get_decision_v2_outcome_leader_heartbeat_seconds()`), not
        cached across a long window. Mirrors `IngestionScheduler.
        is_leader`'s exact contract."""
        return self._is_leader

    @property
    def skipped_due_to_not_leader_count(self) -> int:
        """How many cycle ticks this process has skipped because it was
        not the leader at that tick -- observability only, never used
        for any scheduling decision."""
        return self._skipped_due_to_not_leader_count

    def start(self) -> None:
        if self._task is not None:
            logger.warning("DecisionV2OutcomeScheduler.start() called while already running -- ignoring.")
            return
        # Synchronous first attempt so `is_leader` reflects real state
        # the instant start() returns, rather than depending on
        # asyncio's task-scheduling order to run the heartbeat task's
        # first iteration before the cycle loop's first tick.
        self._is_leader = self._leader_lock.try_acquire_or_renew(get_decision_v2_outcome_leader_lease_seconds())
        self._leadership_task = asyncio.ensure_future(self._leadership_heartbeat_loop())
        self._task = asyncio.ensure_future(self._loop())
        logger.info(
            "DecisionV2OutcomeScheduler started (interval_seconds=%s, is_leader=%s).",
            self._interval_seconds,
            self._is_leader,
        )

    async def stop(self) -> None:
        # Cancel both tasks before awaiting either -- awaiting one hands
        # control back to the event loop, which would otherwise get a
        # chance to run the other task's first real step; cancelling
        # both up front guarantees each is already marked cancelled by
        # the time it actually runs.
        if self._leadership_task is not None:
            self._leadership_task.cancel()
        if self._task is not None:
            self._task.cancel()
        if self._leadership_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._leadership_task
            self._leadership_task = None
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._leader_lock.release()
        self._is_leader = False
        logger.info("DecisionV2OutcomeScheduler stopped.")

    async def _leadership_heartbeat_loop(self) -> None:
        """Renews (or re-attempts) this worker's decision-v2-outcome-
        scheduler lease on a short, fixed cadence -- deliberately
        independent of this scheduler's own (much longer) cycle
        interval, so leadership itself fails over to another worker
        within roughly one heartbeat interval of the previous leader's
        process dying, even though that new leader's first actual
        evaluation cycle still waits for the scheduler's own normal
        schedule (see `_loop`)."""
        heartbeat_seconds = get_decision_v2_outcome_leader_heartbeat_seconds()
        lease_seconds = get_decision_v2_outcome_leader_lease_seconds()
        while True:
            await asyncio.sleep(heartbeat_seconds)
            try:
                self._is_leader = self._leader_lock.try_acquire_or_renew(lease_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- a heartbeat failure must never crash the process; fail closed instead
                logger.exception("DecisionV2OutcomeScheduler: unexpected error during leadership heartbeat.")
                self._is_leader = False

    async def _loop(self) -> None:
        while True:
            try:
                if self._is_leader:
                    await self._run_one_cycle()
                else:
                    # Another worker holds the decision-v2-outcome-
                    # scheduler lease -- this tick is skipped entirely:
                    # zero DB writes, no evaluation-cycle log line. See
                    # the class docstring for the 2026-08-18 multi-
                    # worker duplicate-cycle evidence this closes.
                    self._skipped_due_to_not_leader_count += 1
                    logger.debug(
                        "DecisionV2OutcomeScheduler: not leader this tick -- skipping evaluation cycle."
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error evaluating pending DecisionV2Outcome rows.")
            await asyncio.sleep(self._interval_seconds)

    async def _run_one_cycle(self) -> None:
        session = self._session_factory()
        try:
            summary = await asyncio.to_thread(evaluate_pending_outcomes, session)
            logger.info(
                "DecisionV2Outcome evaluation cycle: %d evaluated, %d data-unavailable, "
                "%d cancelled, %d still pending.",
                summary.evaluated_terminal,
                summary.data_unavailable,
                summary.cancelled,
                summary.still_pending,
            )
        finally:
            session.close()
