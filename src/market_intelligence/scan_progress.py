"""ScanProgressTracker: makes a running full-market scan observable
without depending on GitHub Actions' log API, which returns HTTP 404
for a job's logs while it is still `in_progress` (confirmed directly,
2026-08-02) -- there is no way to poll "how far along is this job"
from outside the job while it runs. This module is Basirah publishing
its own progress instead of waiting for GitHub to expose one.

Three durable outputs are updated after every symbol reaches a
terminal outcome, in this order:

1. `market_scan_progress` DB row (MarketScanProgress, one per
   MarketScanRun) -- durable, queryable independently of the running
   process, survives the process dying mid-scan.
2. `<output_dir>/live_progress.json` -- a plain file a human (or a
   future `tail -f` / polling script) can read directly off the
   runner's filesystem while the step is still running.
3. `$GITHUB_STEP_SUMMARY` -- overwritten (not appended) on every
   update, so the GitHub Actions UI's own run-summary page shows
   current state live, without needing log access at all. Safe to
   open in 'w' mode here because this step is the only one in the
   workflow that writes to the summary while it runs (the "Final
   summary" step runs afterward, in append mode).

Never raises out of a progress-recording call: a bug in progress
tracking must never abort or corrupt the real scan it's observing.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from src.domain.models import MarketScanProgress
from src.market_intelligence.publication_gate import evaluate_publication
from src.market_intelligence.types import PublicationStatus, SymbolScanOutcome

logger = logging.getLogger(__name__)


@dataclass
class _ProgressState:
    run_id: int
    workflow_run_id: Optional[str]
    commit_sha: Optional[str]
    branch: Optional[str]
    mode: Optional[str]
    eligible_discovered: int
    status: str = "RUNNING"
    completed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    insufficient_data_count: int = 0
    published_count: int = 0
    rejected_count: int = 0
    watch_only_count: int = 0
    not_evaluated_count: int = 0
    wait_for_entry_count: int = 0
    current_symbol: Optional[str] = None
    current_symbol_name_en: Optional[str] = None
    current_symbol_name_ar: Optional[str] = None
    last_completed_symbol: Optional[str] = None
    api_calls_total: int = 0
    retries_total: int = 0
    latest_error: Optional[str] = None
    latest_warning: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ScanProgressTracker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        run_id: int,
        eligible_discovered: int,
        output_dir: Optional[Path] = None,
        symbol_names: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
        workflow_run_id: Optional[str] = None,
        commit_sha: Optional[str] = None,
        branch: Optional[str] = None,
        mode: Optional[str] = None,
        api_call_counter: Optional[Callable[[], int]] = None,
    ):
        self._session_factory = session_factory
        self._output_dir = output_dir
        self._symbol_names = symbol_names or {}
        self._api_call_counter = api_call_counter
        self._state = _ProgressState(
            run_id=run_id,
            workflow_run_id=workflow_run_id,
            commit_sha=commit_sha,
            branch=branch,
            mode=mode,
            eligible_discovered=eligible_discovered,
        )
        self._start_monotonic = time.monotonic()
        self._db_row_id: Optional[int] = None
        self._create_row()
        self._flush()

    # -- MarketScanner hook points -----------------------------------

    def on_symbol_start(self, symbol: str) -> None:
        try:
            names = self._symbol_names.get(symbol, {})
            self._state.current_symbol = symbol
            self._state.current_symbol_name_en = names.get("name_en")
            self._state.current_symbol_name_ar = names.get("name_ar")
            self._flush()
        except Exception:  # noqa: BLE001 -- progress tracking must never break the real scan
            logger.exception("ScanProgressTracker.on_symbol_start failed for %s", symbol)

    def on_symbol_complete(self, outcome: SymbolScanOutcome) -> None:
        try:
            self._state.completed_count += 1
            self._state.last_completed_symbol = outcome.symbol
            self._state.current_symbol = None
            self._state.current_symbol_name_en = None
            self._state.current_symbol_name_ar = None

            if outcome.success:
                self._state.success_count += 1
                evaluation = evaluate_publication(outcome)
                if evaluation.status == PublicationStatus.PUBLISHED:
                    self._state.published_count += 1
                elif evaluation.status == PublicationStatus.REJECTED:
                    self._state.rejected_count += 1
                elif evaluation.status == PublicationStatus.WATCH_ONLY:
                    self._state.watch_only_count += 1
                elif evaluation.status == PublicationStatus.WAIT_FOR_ENTRY:
                    self._state.wait_for_entry_count += 1
                else:
                    self._state.not_evaluated_count += 1
            elif outcome.skipped_reason == "insufficient_data":
                self._state.insufficient_data_count += 1
            elif outcome.error is not None:
                self._state.failed_count += 1
                self._state.latest_error = f"{outcome.symbol}: {outcome.error}"
            else:
                self._state.skipped_count += 1

            if self._api_call_counter is not None:
                self._state.api_calls_total = self._api_call_counter()
            self._flush()
        except Exception:  # noqa: BLE001
            logger.exception("ScanProgressTracker.on_symbol_complete failed for %s", outcome.symbol)

    def on_retry(self, symbol: str, attempt: int, max_attempts: int, exc: Exception) -> None:
        try:
            self._state.retries_total += 1
            self._state.latest_warning = f"{symbol}: attempt {attempt}/{max_attempts} failed: {exc}"
            self._flush()
        except Exception:  # noqa: BLE001
            logger.exception("ScanProgressTracker.on_retry failed for %s", symbol)

    def finalize(self, status: str) -> None:
        try:
            self._state.status = status
            self._state.completed_at = datetime.now(timezone.utc)
            self._state.current_symbol = None
            self._flush()
        except Exception:  # noqa: BLE001
            logger.exception("ScanProgressTracker.finalize failed")

    # -- internal ------------------------------------------------------

    def _create_row(self) -> None:
        session = self._session_factory()
        try:
            row = MarketScanProgress(
                run_id=self._state.run_id,
                workflow_run_id=self._state.workflow_run_id,
                commit_sha=self._state.commit_sha,
                branch=self._state.branch,
                mode=self._state.mode,
                status=self._state.status,
                eligible_discovered=self._state.eligible_discovered,
                started_at=self._state.started_at,
                updated_at=self._state.started_at,
            )
            session.add(row)
            session.commit()
            self._db_row_id = row.id
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("ScanProgressTracker._create_row failed (progress DB row not created)")
        finally:
            session.close()

    def _flush(self) -> None:
        self._state.updated_at = datetime.now(timezone.utc)
        self._write_db_row()
        self._write_progress_file()
        self._write_step_summary()

    def _write_db_row(self) -> None:
        if self._db_row_id is None:
            return
        session = self._session_factory()
        try:
            row = session.get(MarketScanProgress, self._db_row_id)
            if row is None:
                return
            s = self._state
            row.status = s.status
            row.completed_count = s.completed_count
            row.success_count = s.success_count
            row.failed_count = s.failed_count
            row.skipped_count = s.skipped_count
            row.insufficient_data_count = s.insufficient_data_count
            row.published_count = s.published_count
            row.rejected_count = s.rejected_count
            row.watch_only_count = s.watch_only_count
            row.not_evaluated_count = s.not_evaluated_count
            row.wait_for_entry_count = s.wait_for_entry_count
            row.current_symbol = s.current_symbol
            row.current_symbol_name_en = s.current_symbol_name_en
            row.current_symbol_name_ar = s.current_symbol_name_ar
            row.last_completed_symbol = s.last_completed_symbol
            row.api_calls_total = s.api_calls_total
            row.retries_total = s.retries_total
            row.latest_error = s.latest_error
            row.latest_warning = s.latest_warning
            row.updated_at = s.updated_at
            row.completed_at = s.completed_at
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("ScanProgressTracker._write_db_row failed")
        finally:
            session.close()

    def as_dict(self) -> Dict[str, object]:
        s = self._state
        elapsed_seconds = time.monotonic() - self._start_monotonic
        remaining = max(0, s.eligible_discovered - s.completed_count)
        avg_seconds_per_symbol = (elapsed_seconds / s.completed_count) if s.completed_count else None
        estimated_remaining_seconds = (
            avg_seconds_per_symbol * remaining if avg_seconds_per_symbol is not None else None
        )
        progress_pct = (
            round(100.0 * s.completed_count / s.eligible_discovered, 2) if s.eligible_discovered else 0.0
        )
        return {
            "run_id": s.run_id,
            "workflow_run_id": s.workflow_run_id,
            "commit_sha": s.commit_sha,
            "branch": s.branch,
            "mode": s.mode,
            "status": s.status,
            "eligible_discovered": s.eligible_discovered,
            "completed_count": s.completed_count,
            "remaining_count": remaining,
            "progress_pct": progress_pct,
            "success_count": s.success_count,
            "failed_count": s.failed_count,
            "skipped_count": s.skipped_count,
            "insufficient_data_count": s.insufficient_data_count,
            "published_count": s.published_count,
            "rejected_count": s.rejected_count,
            "watch_only_count": s.watch_only_count,
            "not_evaluated_count": s.not_evaluated_count,
            "wait_for_entry_count": s.wait_for_entry_count,
            "current_symbol": s.current_symbol,
            "current_symbol_name_en": s.current_symbol_name_en,
            "current_symbol_name_ar": s.current_symbol_name_ar,
            "last_completed_symbol": s.last_completed_symbol,
            "api_calls_total": s.api_calls_total,
            "retries_total": s.retries_total,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "average_seconds_per_symbol": round(avg_seconds_per_symbol, 2) if avg_seconds_per_symbol else None,
            "estimated_remaining_seconds": (
                round(estimated_remaining_seconds, 1) if estimated_remaining_seconds is not None else None
            ),
            "latest_error": s.latest_error,
            "latest_warning": s.latest_warning,
            "started_at": s.started_at.isoformat(),
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }

    def _write_progress_file(self) -> None:
        if self._output_dir is None:
            return
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            path = self._output_dir / "live_progress.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.as_dict(), fh, indent=2, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            logger.exception("ScanProgressTracker._write_progress_file failed")

    def _write_step_summary(self) -> None:
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if not summary_path:
            return
        try:
            d = self.as_dict()
            lines = [
                "# Basirah -- Live Full-Market Scan Progress",
                "",
                f"- Run ID: `{d['run_id']}` | Status: **{d['status']}** | Mode: `{d['mode']}`",
                f"- Commit: `{d['commit_sha']}` | Branch: `{d['branch']}`",
                f"- Progress: **{d['completed_count']} / {d['eligible_discovered']}** "
                f"({d['progress_pct']}%) | Remaining: {d['remaining_count']}",
                f"- Current symbol: **{d['current_symbol'] or '-'}** "
                f"({d['current_symbol_name_en'] or '-'} / {d['current_symbol_name_ar'] or '-'})",
                f"- Last completed: {d['last_completed_symbol'] or '-'}",
                f"- SUCCESS: {d['success_count']} | FAILED: {d['failed_count']} | "
                f"SKIPPED: {d['skipped_count']} | INSUFFICIENT_DATA: {d['insufficient_data_count']}",
                f"- PUBLISHED: {d['published_count']} | REJECTED: {d['rejected_count']} | "
                f"WATCH_ONLY: {d['watch_only_count']} | WAIT_FOR_ENTRY: {d['wait_for_entry_count']} | "
                f"NOT_EVALUATED: {d['not_evaluated_count']}",
                f"- Elapsed: {d['elapsed_seconds']}s | Avg/symbol: {d['average_seconds_per_symbol']}s | "
                f"Est. remaining: {d['estimated_remaining_seconds']}s",
                f"- API calls so far: {d['api_calls_total']} | Retries: {d['retries_total']}",
                f"- Last heartbeat: {d['updated_at']}",
                f"- Latest error: {d['latest_error'] or '-'}",
                f"- Latest warning: {d['latest_warning'] or '-'}",
                "",
            ]
            with open(summary_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
        except Exception:  # noqa: BLE001
            logger.exception("ScanProgressTracker._write_step_summary failed")
