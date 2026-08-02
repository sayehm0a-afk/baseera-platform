"""MarketScanProgress: a durable, continuously-updated progress record
for one MarketScanRun, read/written independently of the run's own
final counters (see market_scan_run.py, which is only ever written
once at the end via finish_run()).

Exists specifically because GitHub Actions exposes no per-symbol
progress while a job is `in_progress` -- confirmed during the
2026-08-02 full-market validation sessions: the job-logs API returns
HTTP 404 until the job completes, and the underlying blob-storage log
URL is blocked by this environment's egress proxy. A scan running
inside a single long-lived GitHub Actions step is otherwise
completely opaque until it finishes. This table, updated after every
symbol via ScanProgressTracker (scan_progress.py), is Basirah
publishing its own progress rather than depending on GitHub's.

One row per MarketScanRun (run_id is unique), so polling progress is
a single indexed lookup, not a scan of symbol_intelligence_records.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class MarketScanProgress(Base):
    __tablename__ = "market_scan_progress"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("market_scan_runs.id"), nullable=False, unique=True, index=True)

    workflow_run_id = Column(String(64), nullable=True)
    commit_sha = Column(String(64), nullable=True)
    branch = Column(String(255), nullable=True)
    mode = Column(String(32), nullable=True)

    status = Column(String(32), nullable=False, default="RUNNING", server_default="RUNNING")

    eligible_discovered = Column(Integer, nullable=False, default=0, server_default="0")
    completed_count = Column(Integer, nullable=False, default=0, server_default="0")
    success_count = Column(Integer, nullable=False, default=0, server_default="0")
    failed_count = Column(Integer, nullable=False, default=0, server_default="0")
    skipped_count = Column(Integer, nullable=False, default=0, server_default="0")
    insufficient_data_count = Column(Integer, nullable=False, default=0, server_default="0")

    # Publication-gate breakdown (see publication_gate.py) -- distinct
    # from the scan-terminal-outcome counts above: only a symbol that
    # reached SUCCESS is ever evaluated for publication, and its
    # verdict (PUBLISHED/REJECTED/NOT_EVALUATED) is a separate,
    # later-stage classification, not a sixth scan-outcome bucket.
    published_count = Column(Integer, nullable=False, default=0, server_default="0")
    rejected_count = Column(Integer, nullable=False, default=0, server_default="0")
    watch_only_count = Column(Integer, nullable=False, default=0, server_default="0")
    not_evaluated_count = Column(Integer, nullable=False, default=0, server_default="0")

    current_symbol = Column(String(32), nullable=True)
    current_symbol_name_en = Column(String(255), nullable=True)
    current_symbol_name_ar = Column(String(255), nullable=True)
    last_completed_symbol = Column(String(32), nullable=True)

    api_calls_total = Column(Integer, nullable=False, default=0, server_default="0")
    retries_total = Column(Integer, nullable=False, default=0, server_default="0")

    latest_error = Column(Text, nullable=True)
    latest_warning = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<MarketScanProgress run_id={self.run_id} status={self.status} {self.completed_count}/{self.eligible_discovered}>"
