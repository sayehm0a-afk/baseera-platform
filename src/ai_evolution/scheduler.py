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
    get_outcome_evaluation_interval_seconds,
    get_pattern_discovery_interval_seconds,
)
from src.ai_evolution.outcome_evaluation import evaluate_due_outcomes
from src.ai_evolution.pattern_discovery import discover_patterns

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
