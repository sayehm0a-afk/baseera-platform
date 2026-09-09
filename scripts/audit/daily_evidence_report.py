"""Read-only daily Decision V2 evidence inventory; never invokes a scanner.

Use a read-only database credential in BASIRAH_AUDIT_DATABASE_URL.
Results describe issuance cohorts as observed now, not historical as-of outcomes.
"""

import argparse
import json
import os
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import MetaData, Table, create_engine, select

RIYADH = ZoneInfo("Asia/Riyadh")
ACTIONABLE = {"BUY_CANDIDATE", "STRONG_BUY_CANDIDATE"}


def build_report(connection, day: date) -> dict:
    metadata = MetaData()
    snapshots = Table("decision_v2_snapshots", metadata, autoload_with=connection)
    outcomes = Table("decision_v2_outcomes", metadata, autoload_with=connection)
    start = datetime.combine(day, time.min, RIYADH).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    query = select(
        snapshots.c.id, snapshots.c.decision, snapshots.c.engine_sha,
        snapshots.c.config_hash, snapshots.c.quote_timestamp,
        snapshots.c.is_real_data, snapshots.c.is_synthetic,
        outcomes.c.id.label("outcome_id"), outcomes.c.status,
        outcomes.c.entry_triggered, outcomes.c.is_independent_signal,
        outcomes.c.last_checked_at,
    ).select_from(snapshots.outerjoin(
        outcomes, outcomes.c.decision_v2_snapshot_id == snapshots.c.id
    )).where(snapshots.c.decision_timestamp >= start,
             snapshots.c.decision_timestamp < end)
    counts = Counter()
    statuses = Counter()
    cohorts = Counter()
    last_checked = None
    seen = set()
    for row in connection.execute(query).mappings():
        if row["id"] in seen:
            raise ValueError("Duplicate outcome linkage; report rejected rather than double counted")
        seen.add(row["id"])
        counts["decision_snapshots"] += 1
        actionable = row["decision"] in ACTIONABLE
        counts["actionable_snapshots"] += int(actionable)
        counts["actionable_without_outcome"] += int(actionable and row["outcome_id"] is None)
        counts["missing_quote_timestamp"] += int(row["quote_timestamp"] is None)
        counts["real_data_not_confirmed"] += int(row["is_real_data"] is not True or row["is_synthetic"] is not False)
        cohorts[(row["engine_sha"] or "UNKNOWN", row["config_hash"] or "UNKNOWN")] += 1
        if row["outcome_id"] is None:
            continue
        counts["outcome_records"] += 1
        counts["entry_triggered"] += int(row["entry_triggered"] is True)
        counts["independent_signals"] += int(row["is_independent_signal"] is True)
        counts["continuations"] += int(row["is_independent_signal"] is False)
        counts["unknown_independence"] += int(row["is_independent_signal"] is None)
        statuses[str(row["status"])] += 1
        checked = row["last_checked_at"]
        if checked is not None:
            checked = checked.replace(tzinfo=timezone.utc) if checked.tzinfo is None else checked
            last_checked = checked if last_checked is None else max(last_checked, checked)
    keys = ("decision_snapshots", "actionable_snapshots", "actionable_without_outcome",
            "missing_quote_timestamp", "real_data_not_confirmed", "outcome_records",
            "entry_triggered", "independent_signals", "continuations", "unknown_independence")
    return {
        "schema_version": 1,
        "report_kind": "issuance_cohort_inventory_not_performance_proof",
        "issuance_day_riyadh": day.isoformat(), "timezone": "Asia/Riyadh",
        "window_utc": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "counts": {key: counts[key] for key in keys},
        "outcome_status_counts": dict(sorted(statuses.items())),
        "cohorts": [{"engine_sha": engine, "config_hash": config, "snapshots": count}
                    for (engine, config), count in sorted(cohorts.items())],
        "latest_outcome_check_at": last_checked.isoformat() if last_checked else None,
        "performance": {"win_rate": None, "expected_return": None, "net_return": None,
                        "portfolio_drawdown": None, "longest_loss_streak": None},
        "limitations": [
            "Counts reflect stored rows, not completeness of all recommendations shown.",
            "PARTIAL means ambiguous ordering, never a proven win or loss.",
            "A decision snapshot is not necessarily an independent trade.",
            "No cost, execution, portfolio allocation, or live-provider proof is inferred.",
            "Outcomes are current observations of this issuance cohort, not a historical as-of reconstruction.",
            "This command does not schedule monitoring, ingest prices, evaluate outcomes, or issue recommendations.",
        ],
    }


def write_report(report: dict, destination: Path) -> None:
    # Refuse to overwrite an earlier observation.
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database_url = os.environ.get("BASIRAH_AUDIT_DATABASE_URL")
    if not database_url:
        parser.error("BASIRAH_AUDIT_DATABASE_URL must contain a read-only database connection")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                connection.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
            elif engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                raise ValueError("Only PostgreSQL and SQLite are supported")
            report = build_report(connection, args.day)
        write_report(report, args.output)
    except Exception as exc:
        # Connection exceptions may contain URLs/credentials: never print their text.
        raise SystemExit(f"Report failed ({type(exc).__name__}); no success claimed") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
