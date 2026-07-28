#!/usr/bin/env python3
"""L2 live pipeline validation: a real, unmocked, end-to-end run of
Basirah's production pipeline -- SAHMK ingestion -> PostgreSQL ->
technical/fundamental analysis -> AI decision engine -> confidence ->
recommendation storage -- against the live SAHMK API and a real,
ephemeral PostgreSQL database, on a GitHub-hosted runner (see
.github/workflows/sahmk-live-pipeline-validation.yml), because this
repository's Claude Code sandbox has no egress to app.sahmk.sa (see
docs/SAHMK_INTEGRATION.md).

This script contains ZERO new business logic -- every step below calls
existing, unmodified production code (src.market_data.ingestion.*,
src.market_intelligence.*, src.market_intelligence.live_market_mode).
It only orchestrates those real calls, prints redacted evidence, and
asserts integrity against the real database afterward.

Hard gate: if MARKET_DATA_PROVIDER resolves to anything other than
"sahmk" -- i.e. provider_factory silently fell back to the synthetic
DevMarketDataProvider because SAHMK was unreachable even from this
runner -- this script aborts immediately (exit 1) rather than
proceeding to generate and store synthetic "recommendations." See
_require_live_providers() below. This is the one hard rule this
validation exists to enforce.

Usage:
    DATABASE_URL=postgresql://... SAHMK_API_KEY=... \\
        python3 scripts/verify_sahmk_live_pipeline.py

Exit code: 0 if the core pipeline (live providers confirmed, ingestion,
scan, storage, integrity) completed successfully -- even if the Live
Market Mode soak test only observed the "market closed" branch, which
is still a valid, correctly-behaving result for that one item. Exit 1
on a genuine failure: SAHMK unreachable, a silent dev-provider
fallback, zero recommendations generated, or a database integrity
violation.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.ai_evolution.outcome_evaluation import EVALUATION_HORIZON_DAYS  # noqa: E402
from src.domain.models import (  # noqa: E402
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)
from src.market_data.fundamental_provider_factory import (  # noqa: E402
    get_fundamental_data_provider,
    get_last_selected_fundamental_provider_kind,
)
from src.market_data.ingestion import config as ingestion_config  # noqa: E402
from src.market_data.ingestion.ingest_dividends import ingest_dividends  # noqa: E402
from src.market_data.ingestion.ingest_fundamentals import ingest_fundamentals  # noqa: E402
from src.market_data.ingestion.ingest_historical_ohlcv import ingest_historical_ohlcv  # noqa: E402
from src.market_data.ingestion.ingest_symbols import sync_symbols  # noqa: E402
from src.market_data.ingestion.scheduler import IngestionScheduler  # noqa: E402
from src.market_data.provider_factory import get_market_data_provider, get_last_selected_provider_kind  # noqa: E402
from src.market_intelligence.live_market_mode import LiveMarketModeScheduler  # noqa: E402
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository  # noqa: E402
from src.market_intelligence.scheduler import IntervalMarketIntelligenceScheduler  # noqa: E402
from src.market_intelligence.services.scan_job_runner import run_market_scan_job  # noqa: E402
from src.market_intelligence.trading_calendar import (  # noqa: E402
    TADAWUL_TIMEZONE,
    is_market_open,
    seconds_until_close,
)

DEFAULT_SYMBOLS = ["2222", "2010", "1120", "7010", "1180"]


def _redact(text_value: str) -> str:
    key = os.getenv("SAHMK_API_KEY", "")
    return text_value.replace(key, "***REDACTED***") if key and key in text_value else text_value


def _print(line: str = "") -> None:
    print(_redact(str(line)))


def _section(title: str) -> None:
    _print()
    _print("=" * 70)
    _print(f" {title}")
    _print("=" * 70)


class ValidationFailure(Exception):
    pass


async def _require_live_providers() -> None:
    """The hard gate. Never continue this script against synthetic data."""
    market_provider = await get_market_data_provider(force_refresh=True)
    market_kind = get_last_selected_provider_kind()
    fundamental_provider = await get_fundamental_data_provider(force_refresh=True)
    fundamental_kind = get_last_selected_fundamental_provider_kind()

    _print(f"Market data provider selected: {market_kind!r}")
    _print(f"Fundamental data provider selected: {fundamental_kind!r}")

    if market_kind != "sahmk" or fundamental_kind != "sahmk":
        raise ValidationFailure(
            "ABORTED_DEV_FALLBACK: provider_factory did not select the live SAHMK "
            f"provider (market={market_kind!r}, fundamental={fundamental_kind!r}). "
            "This means SAHMK was unreachable or rejected authentication even from "
            "this GitHub-hosted runner. Refusing to proceed against synthetic data -- "
            "see the diagnosis workflow (sahmk-live-verification.yml) for root cause."
        )
    return market_provider, fundamental_provider


async def _run_ingestion(symbols: List[str], market_provider, fundamental_provider, session_factory) -> Dict[str, object]:
    _section("STEP 5a: Ingestion (real SAHMK calls, real DB writes)")
    results = {}

    _print(f"Symbol universe: {symbols}")

    _print("\n-- sync_symbols --")
    results["symbols"] = await sync_symbols(symbols, market_provider, session_factory, discover_all=False)
    _print(vars(results["symbols"]))

    _print("\n-- ingest_historical_ohlcv --")
    results["historical_ohlcv"] = await ingest_historical_ohlcv(
        symbols, market_provider, session_factory, backfill_days=ingestion_config.get_ohlcv_backfill_days()
    )
    _print(vars(results["historical_ohlcv"]))

    _print("\n-- ingest_fundamentals --")
    results["fundamentals"] = await ingest_fundamentals(
        symbols, fundamental_provider, session_factory, period_type=ingestion_config.get_fundamentals_period_type()
    )
    _print(vars(results["fundamentals"]))

    _print("\n-- ingest_dividends --")
    results["dividends"] = await ingest_dividends(symbols, fundamental_provider, session_factory)
    _print(vars(results["dividends"]))

    return results


def _verify_stocks_registered(symbols: List[str], session_factory) -> List[str]:
    session = session_factory()
    try:
        registered = {
            row[0] for row in session.query(Stock.symbol).filter(Stock.symbol.in_(symbols)).all()
        }
    finally:
        session.close()
    missing = [s for s in symbols if s not in registered]
    _print(f"Stocks registered after ingestion: {sorted(registered)}")
    if missing:
        _print(f"NOT VERIFIED -- symbols with no Stock row after ingestion: {missing}")
    return sorted(registered)


async def _run_scan(symbols: List[str], market_provider, session_factory) -> int:
    _section("STEP 5b: Market scan (real AnalystEngine -> AIDecisionEngine pipeline)")
    repository = MarketIntelligenceRepository()
    session = session_factory()
    try:
        run = repository.create_scan_run(session, symbols_requested=len(symbols))
        run_id = run.id
    finally:
        session.close()

    await run_market_scan_job(run_id, session_factory, market_provider, symbols=symbols)

    session = session_factory()
    try:
        run = repository.get_run(session, run_id)
        _print(
            f"MarketScanRun {run_id}: status={run.status.value} "
            f"succeeded={run.symbols_succeeded} skipped={run.symbols_skipped} "
            f"failed={run.symbols_failed} duration={run.duration_seconds}s"
        )
    finally:
        session.close()
    return run_id


def _print_recommendations(session_factory) -> List[RecommendationSnapshot]:
    session = session_factory()
    try:
        rows = (
            session.query(RecommendationSnapshot)
            .filter(RecommendationSnapshot.source == "live_scan")
            .order_by(RecommendationSnapshot.id)
            .all()
        )
        _section("STEP 6: Generated recommendations (real, from live data)")
        for row in rows:
            _print(
                f"  {row.symbol}: {row.recommendation.value} "
                f"confidence={row.confidence_score} total_score={row.total_score} "
                f"target={row.target_price} stop={row.stop_loss} "
                f"expected_return_pct={row.expected_return_pct} "
                f"risk_level={row.risk_level} evaluated_at={row.evaluated_at.isoformat()}"
            )
            if row.reasons:
                _print(f"    reasons: {list(row.reasons)[:2]}")
        if not rows:
            _print("  (none -- see scan result above for why)")
        return rows
    finally:
        session.close()


def _verify_database_integrity(session_factory, expected_symbols: List[str]) -> Dict[str, object]:
    _section("STEP 7/8: Database integrity verification")
    session = session_factory()
    checks: Dict[str, object] = {}
    try:
        total = session.query(func.count(RecommendationSnapshot.id)).filter(
            RecommendationSnapshot.source == "live_scan"
        ).scalar()
        checks["total_snapshots"] = total

        distinct_identity = session.query(
            func.count(func.distinct(
                func.concat(RecommendationSnapshot.symbol, "|", RecommendationSnapshot.evaluated_at)
            ))
        ).filter(RecommendationSnapshot.source == "live_scan").scalar()
        checks["no_duplicates"] = (distinct_identity == total)

        null_critical = session.query(func.count(RecommendationSnapshot.id)).filter(
            RecommendationSnapshot.source == "live_scan",
            (
                RecommendationSnapshot.recommendation.is_(None)
                | RecommendationSnapshot.total_score.is_(None)
                | RecommendationSnapshot.confidence_score.is_(None)
                | RecommendationSnapshot.engine_version.is_(None)
                | RecommendationSnapshot.symbol.is_(None)
                | RecommendationSnapshot.evaluated_at.is_(None)
                | RecommendationSnapshot.stock_id.is_(None)
            ),
        ).scalar()
        checks["null_critical_fields"] = null_critical

        orphaned_fk = session.execute(
            text(
                "SELECT COUNT(*) FROM recommendation_snapshots rs "
                "LEFT JOIN stocks s ON s.id = rs.stock_id "
                "WHERE rs.source = 'live_scan' AND s.id IS NULL"
            )
        ).scalar()
        checks["orphaned_stock_fk"] = orphaned_fk

        pending_outcomes = session.query(func.count(RecommendationOutcome.id)).join(
            RecommendationSnapshot, RecommendationSnapshot.id == RecommendationOutcome.snapshot_id
        ).filter(
            RecommendationSnapshot.source == "live_scan",
            RecommendationOutcome.status == RecommendationOutcomeStatus.PENDING,
        ).scalar()
        checks["pending_outcomes"] = pending_outcomes
        checks["expected_pending_outcomes"] = total * len(EVALUATION_HORIZON_DAYS)

        for key, value in checks.items():
            _print(f"  {key}: {value}")

        checks["passed"] = (
            total > 0
            and checks["no_duplicates"]
            and null_critical == 0
            and orphaned_fk == 0
            and pending_outcomes == checks["expected_pending_outcomes"]
        )
        _print(f"  INTEGRITY CHECK: {'PASSED' if checks['passed'] else 'FAILED'}")
        return checks
    finally:
        session.close()


async def _run_live_market_mode_soak(session_factory, market_provider_getter, soak_seconds: float, poll_seconds: float) -> Dict[str, object]:
    _section("STEP 9: Live Market Mode -- real-clock soak test")
    now = datetime.now(timezone.utc)
    market_open_at_start = is_market_open(now)
    _print(f"UTC now: {now.isoformat()}")
    _print(f"Tadawul local now: {now.astimezone(TADAWUL_TIMEZONE).isoformat()}")
    _print(f"is_market_open() at soak start: {market_open_at_start}")
    if market_open_at_start:
        _print(f"seconds_until_close(): {seconds_until_close(now):.0f}")

    baseline_snapshot_count = _count_live_snapshots(session_factory)
    baseline_task_count = len(asyncio.all_tasks())

    ingestion_scheduler = IngestionScheduler(session_factory=session_factory, market_provider_getter=market_provider_getter)
    scan_scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=session_factory, market_provider_getter=market_provider_getter
    )
    live_mode = LiveMarketModeScheduler(
        ingestion_scheduler=ingestion_scheduler,
        market_intelligence_scheduler=scan_scheduler,
        poll_interval_seconds=poll_seconds,
    )

    live_mode.start()
    _print(f"LiveMarketModeScheduler started (poll_interval={poll_seconds}s). Soaking for {soak_seconds}s...")
    await asyncio.sleep(soak_seconds)

    observed_open = live_mode.is_market_currently_open
    inner_ingestion_running = ingestion_scheduler.is_running
    inner_scan_running = scan_scheduler.is_running

    await live_mode.stop()
    after_stop_task_count = len(asyncio.all_tasks())
    post_snapshot_count = _count_live_snapshots(session_factory)

    result = {
        "market_open_at_start": market_open_at_start,
        "observed_open_after_ticks": observed_open,
        "inner_ingestion_was_running": inner_ingestion_running,
        "inner_scan_was_running": inner_scan_running,
        "inner_schedulers_stopped_cleanly": (not ingestion_scheduler.is_running) and (not scan_scheduler.is_running),
        "baseline_snapshot_count": baseline_snapshot_count,
        "post_soak_snapshot_count": post_snapshot_count,
        "new_snapshots_from_auto_scan": post_snapshot_count - baseline_snapshot_count,
        "baseline_task_count": baseline_task_count,
        "after_stop_task_count": after_stop_task_count,
        "no_leaked_tasks": after_stop_task_count <= baseline_task_count,
    }
    for key, value in result.items():
        _print(f"  {key}: {value}")
    return result


def _count_live_snapshots(session_factory) -> int:
    session = session_factory()
    try:
        return session.query(func.count(RecommendationSnapshot.id)).filter(
            RecommendationSnapshot.source == "live_scan"
        ).scalar()
    finally:
        session.close()


def _write_github_summary(lines: List[str]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(_redact(line) + "\n")


async def main() -> int:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url or database_url.startswith("sqlite"):
        _print("FATAL: DATABASE_URL must point to a real PostgreSQL instance -- refusing to run against sqlite.")
        return 1

    symbols = [s.strip() for s in os.getenv("LIVE_PIPELINE_SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",") if s.strip()]
    soak_seconds = float(os.getenv("LIVE_MARKET_MODE_SOAK_SECONDS", "45"))
    poll_seconds = float(os.getenv("LIVE_MARKET_MODE_SOAK_POLL_SECONDS", "5"))

    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)

    summary_lines = ["# Basirah L2 -- Live Pipeline Validation\n"]

    try:
        _section("STEP 1-4: SAHMK connectivity + provider selection")
        market_provider, fundamental_provider = await _require_live_providers()

        await _run_ingestion(symbols, market_provider, fundamental_provider, session_factory)
        registered_symbols = _verify_stocks_registered(symbols, session_factory)

        if not registered_symbols:
            raise ValidationFailure("No symbols were successfully registered -- nothing to scan.")

        await _run_scan(registered_symbols, market_provider, session_factory)
        recommendations = _print_recommendations(session_factory)
        integrity = _verify_database_integrity(session_factory, registered_symbols)

        soak_result = await _run_live_market_mode_soak(
            session_factory, get_market_data_provider, soak_seconds, poll_seconds
        )

        _section("FINAL STATUS")
        core_ok = len(recommendations) > 0 and integrity["passed"]
        _print(f"Symbols requested: {symbols}")
        _print(f"Symbols registered: {registered_symbols}")
        _print(f"Recommendations generated: {len(recommendations)}")
        _print(f"Database integrity: {'PASSED' if integrity['passed'] else 'FAILED'}")
        _print(f"Live Market Mode soak: market_open_at_start={soak_result['market_open_at_start']}")
        status = "PIPELINE_VERIFIED" if core_ok else "PIPELINE_FAILED"
        _print(f"FINAL_STATUS={status}")

        summary_lines += [
            f"- SAHMK live providers confirmed: **YES** (market={get_last_selected_provider_kind()}, "
            f"fundamental={get_last_selected_fundamental_provider_kind()})",
            f"- Symbols requested: `{symbols}`",
            f"- Symbols registered: `{registered_symbols}`",
            f"- Recommendations generated: **{len(recommendations)}**",
            f"- Database integrity: **{'PASSED' if integrity['passed'] else 'FAILED'}** ({integrity})",
            f"- Live Market Mode soak: market_open_at_start=**{soak_result['market_open_at_start']}**, "
            f"observed_open_after_ticks={soak_result['observed_open_after_ticks']}, "
            f"new_snapshots_from_auto_scan={soak_result['new_snapshots_from_auto_scan']}, "
            f"no_leaked_tasks={soak_result['no_leaked_tasks']}",
            f"- FINAL_STATUS={status}",
        ]
        _write_github_summary(summary_lines)
        return 0 if core_ok else 1

    except ValidationFailure as exc:
        _print(f"\nFINAL_STATUS=ABORTED\n{exc}")
        summary_lines.append(f"- **ABORTED**: {exc}")
        _write_github_summary(summary_lines)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
