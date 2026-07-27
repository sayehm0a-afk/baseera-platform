#!/usr/bin/env python3
"""Data-retention cleanup CLI (Phase 13, P13.6).

Runs `src.auth.retention_cleanup_service.run_retention_cleanup` once
and prints a summary of what was deleted. Not wired to a live scheduler
in this milestone -- intended to be invoked by an operator, a one-off
cron entry, or a future scheduled-job milestone (the same "build the
callable service now, wire scheduling later" pattern this codebase
already uses for `src.market_data.ingestion.scheduler`/
`src.market_intelligence.scheduler`, both of which existed as plain
functions before either got a live scheduler on top).

Usage:
    DATABASE_URL=postgresql://... python3 scripts/run_retention_cleanup.py

Safe to run repeatedly -- see retention_cleanup_service.py's own
docstring for the idempotency argument.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth.retention_cleanup_service import run_retention_cleanup  # noqa: E402
from src.core.db.database import get_session_factory  # noqa: E402


def main() -> None:
    session = get_session_factory()()
    try:
        summary = run_retention_cleanup(session)
    finally:
        session.close()

    print(f"Sessions deleted: {summary.sessions_deleted}")
    print(f"Email verification tokens deleted: {summary.email_verification_tokens_deleted}")
    print(f"Password reset tokens deleted: {summary.password_reset_tokens_deleted}")
    print(f"Total: {summary.total_deleted}")


if __name__ == "__main__":
    main()
