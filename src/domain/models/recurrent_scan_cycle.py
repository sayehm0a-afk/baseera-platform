"""RecurrentScanCycle: the durable, queryable record of one attempt by
the recurrent live-scan scheduler (`src.market_intelligence.
recurrent_live_scan.RecurrentLiveScanScheduler`) to refresh Basirah's
market intelligence during a live Tadawul session -- separate from
`MarketScanRun` (the once-a-day opening scan's own history) because a
recurrent cycle fires far more often and, most cycles, does nothing
material at all (`SUCCESS_NO_CHANGE`) or is deliberately skipped
(market closed, quota protection, lock contention) rather than run.

This is Shadow Mode's audit trail, not a second decision engine: every
cycle either reuses the existing Stage 1 (`stage1_local_scan.py`) /
Stage 2 (`run_market_scan_job`) / Decision V2 pipeline unmodified, or
records exactly why it did not run one this tick. `scan_run_id` links
back to the real `MarketScanRun` Stage 2 wrote when a cycle actually
executed live validation -- never a second, parallel scan-run concept.

One row per cycle, written once at cycle start (PENDING-like fields
filled progressively) and finalized when the cycle ends -- there is no
started_at/finished_at ambiguity like MarketScanRun's PENDING/RUNNING
window because a recurrent cycle is short-lived and synchronous within
the scheduler's own loop tick, never left half-written across a
process restart the way a long scan could be.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Enum, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class RecurrentScanCycleStatus(str, enum.Enum):
    # A cycle that actually ran Stage 2 and emitted at least one
    # ShadowLiveSignal (a material change was found for at least one
    # evaluated symbol).
    SUCCESS = "SUCCESS"
    # A cycle that ran Stage 2 (spent real SAHMK requests) but found no
    # material change for any evaluated symbol -- every candidate's
    # existing shadow state already said the same thing. Distinct from
    # SUCCESS so "the scheduler is alive and working" is never confused
    # with "the scheduler is silently doing nothing."
    SUCCESS_NO_CHANGE = "SUCCESS_NO_CHANGE"
    SKIPPED_MARKET_CLOSED = "SKIPPED_MARKET_CLOSED"
    SKIPPED_QUOTA = "SKIPPED_QUOTA"
    SKIPPED_LOCKED = "SKIPPED_LOCKED"
    SKIPPED_NO_CANDIDATES = "SKIPPED_NO_CANDIDATES"
    # Stage 2 started but did not complete for every selected symbol
    # (e.g. quota was exhausted mid-cycle by a concurrent critical
    # request) -- whatever symbols it did complete are still recorded
    # normally; this status only flags that the cycle's own candidate
    # list was not fully attempted.
    PARTIAL_PROVIDER_FAILURE = "PARTIAL_PROVIDER_FAILURE"
    FAILED = "FAILED"


class RecurrentScanCycle(Base):
    __tablename__ = "recurrent_scan_cycles"

    id = Column(Integer, primary_key=True)

    # A stable, human-shareable identifier independent of the
    # auto-increment id -- included in every log line the scheduler
    # emits for this cycle, so a support/audit conversation can refer to
    # "cycle <cycle_id>" unambiguously even before the row's own id is
    # known (e.g. while still logging pre-commit).
    cycle_id = Column(String(36), nullable=False, unique=True, index=True)

    status = Column(Enum(RecurrentScanCycleStatus), nullable=False, index=True)
    skip_reason = Column(String(64), nullable=True)
    error_summary = Column(Text, nullable=True)

    market_status = Column(String(32), nullable=True)

    # Phase 7/8 candidate-selection funnel: how many symbols entered the
    # bounded Stage 2 slate for each reason, and how many total slots
    # that was capped to. Selection logic itself lives in
    # recurrent_live_scan.py, not here -- these are just the resulting
    # counts, for observability.
    active_signal_candidate_count = Column(Integer, nullable=True)
    new_stage1_candidate_count = Column(Integer, nullable=True)
    symbols_selected_count = Column(Integer, nullable=True)
    symbols_evaluated_count = Column(Integer, nullable=True)

    # PR #107 forensic observability: Stage 1's own top-ranked
    # candidates this cycle (bounded to 10; see
    # `select_recurrent_candidates`'s own docstring), each carrying its
    # already-computed `ranking_score` (never recalculated here),
    # whether it was actually selected into this cycle's bounded Stage
    # 2 slate, and which pool selected it -- so a future audit of a
    # "why did the same symbols repeat" question is directly provable
    # from this row instead of requiring source-code reconstruction.
    # Nullable: absent for every cycle status that never reaches Stage
    # 1 (e.g. SKIPPED_QUOTA, SKIPPED_LOCKED) and for every pre-PR-107
    # historical row.
    top_stage1_candidates = Column(JSON, nullable=True)

    # Phase 9/11 lifecycle-result funnel for this cycle -- mirrors
    # ShadowLifecycleResult's members. signals_unchanged_count is the
    # only one with no corresponding ShadowLiveSignal rows (Phase 9: an
    # unchanged signal is never persisted as a new row).
    signals_new_opportunity_count = Column(Integer, nullable=False, default=0, server_default="0")
    signals_refreshed_count = Column(Integer, nullable=False, default=0, server_default="0")
    signals_missed_entry_count = Column(Integer, nullable=False, default=0, server_default="0")
    signals_chase_risk_count = Column(Integer, nullable=False, default=0, server_default="0")
    signals_invalidated_count = Column(Integer, nullable=False, default=0, server_default="0")
    signals_unchanged_count = Column(Integer, nullable=False, default=0, server_default="0")

    # Phase 2/17 quota-authority evidence, captured before and after
    # this cycle's own Stage 2 spend -- SahmkRateLimiter.get_status()'s
    # own real numbers, never re-derived or estimated.
    quota_remaining_before = Column(Integer, nullable=True)
    quota_remaining_after = Column(Integer, nullable=True)
    requests_used_estimate = Column(Integer, nullable=True)

    # The real MarketScanRun Stage 2 created for this cycle, when Stage
    # 2 actually ran -- null for every skipped-before-Stage-2 status.
    scan_run_id = Column(Integer, nullable=True, index=True)

    triggered_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<RecurrentScanCycle cycle_id={self.cycle_id!r} status={self.status!r}>"
