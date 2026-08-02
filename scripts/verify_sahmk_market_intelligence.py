#!/usr/bin/env python3
"""Basirah Phase 9 -- full Saudi-market Market Intelligence validation.

A real, unmocked run against the entire live SAHMK symbol universe
(Tadawul+Nomu), not a fixed 5-symbol sample: discovers every symbol
SAHMK's own directory reports, ingests real historical OHLCV,
fundamentals, and dividends for all of them, runs the real production
scan pipeline (AnalystEngine -> AIDecisionEngine, unmodified), and
dumps every real per-company technical/fundamental/decision field the
platform actually computes -- not a curated subset -- plus real
rankings, real watchlists, and real per-step timing/API-call
instrumentation.

Contains ZERO new business logic: every analytical result comes from
calling existing, unmodified production code
(sync_symbols/ingest_historical_ohlcv/ingest_fundamentals/
ingest_dividends, MarketIntelligenceEngine.execute_scan, RankingEngine,
WatchlistEngine). This script only orchestrates those real calls,
counts real API calls via the shared rate limiter, and serializes the
real results to a JSON artifact -- there is far too much data (up to
~350 companies x dozens of fields) for GitHub Actions job logs, so the
full dump is written to a file uploaded as a build artifact; only a
condensed summary goes to stdout/$GITHUB_STEP_SUMMARY.

Hard gate: aborts immediately if MARKET_DATA_PROVIDER does not resolve
to "sahmk" for both market and fundamental data -- see
_require_live_providers(). Never proceeds against synthetic data.

Usage:
    DATABASE_URL=postgresql://... SAHMK_API_KEY=... \\
        python3 scripts/verify_sahmk_market_intelligence.py
"""

import asyncio
import csv
import json
import logging
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Python's default root logger level is WARNING with no handler attached
# until something calls basicConfig() -- discovered during the
# 2026-08-02 live full-universe validation runs, where
# src.market_data.sahmk.service.get_company_directory()'s own
# logger.info(...) universe-verdict/pagination diagnostic (pages
# fetched, pagination_signal, reported_total, universe_verdict) was
# silently dropped from every job log, while its logger.warning(...)
# sibling (sector field unresolved) printed fine. That diagnostic is
# exactly the evidence needed to tell a genuine ~100-company universe
# apart from an unnoticed pagination cap, so this script must not run
# with it suppressed.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.domain.models import RecommendationSnapshot, Stock  # noqa: E402
from src.market_data.fundamental_provider_factory import (  # noqa: E402
    get_fundamental_data_provider,
    get_last_selected_fundamental_provider_kind,
)
from src.market_data.ingestion import config as ingestion_config  # noqa: E402
from src.market_data.ingestion.ingest_dividends import ingest_dividends  # noqa: E402
from src.market_data.ingestion.ingest_fundamentals import ingest_fundamentals  # noqa: E402
from src.market_data.ingestion.ingest_historical_ohlcv import ingest_historical_ohlcv  # noqa: E402
from src.market_data.ingestion.ingest_symbols import sync_symbols  # noqa: E402
from src.market_data.provider_factory import get_market_data_provider, get_last_selected_provider_kind  # noqa: E402
from src.market_data.sahmk.rate_limiter import get_default_rate_limiter  # noqa: E402
from src.market_intelligence.market_engine import MarketIntelligenceEngine  # noqa: E402
from src.market_intelligence.ranking import RankingEngine  # noqa: E402
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository  # noqa: E402
from src.market_intelligence.trading_calendar import TADAWUL_TIMEZONE, is_market_open  # noqa: E402
from src.market_intelligence.universe_policy import classify_universe  # noqa: E402
from src.market_intelligence.watchlist import WatchlistEngine  # noqa: E402

OUTPUT_DIR = Path(os.getenv("MARKET_INTELLIGENCE_OUTPUT_DIR", "market_intelligence_output"))


def _redact(text_value: str) -> str:
    key = os.getenv("SAHMK_API_KEY", "")
    return text_value.replace(key, "***REDACTED***") if key and key in text_value else text_value


def _print(line: str = "") -> None:
    print(_redact(str(line)))


def _section(title: str) -> None:
    _print()
    _print("=" * 78)
    _print(f" {title}")
    _print("=" * 78)


class ValidationFailure(Exception):
    pass


def _json_default(value: Any) -> Any:
    """Best-effort JSON serialization for whatever real engine output
    shows up (Decimal, datetime/date, enums, dataclasses, pandas
    NaN-ish floats) -- never fabricates a value, only reshapes types
    JSON can't natively carry."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "value") and isinstance(getattr(value, "value"), (str, int, float)):
        return value.value
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    return str(value)


class _RateLimiterCallCounter:
    """Wraps the real, shared SahmkRateLimiter's acquire() to count
    genuine outbound SAHMK requests for this run -- every SahmkClient
    call goes through this singleton's acquire() before hitting the
    network, so this is an exact count, not an estimate."""

    def __init__(self):
        self.count = 0
        self._limiter = get_default_rate_limiter()
        self._original_acquire = self._limiter.acquire

        async def _counting_acquire():
            self.count += 1
            await self._original_acquire()

        self._limiter.acquire = _counting_acquire

    def restore(self) -> None:
        self._limiter.acquire = self._original_acquire


async def _require_live_providers():
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
            "Refusing to proceed against synthetic data."
        )
    return market_provider, fundamental_provider


def _all_registered_symbols(session_factory) -> List[Dict[str, Any]]:
    session = session_factory()
    try:
        rows = session.query(Stock).filter(Stock.is_active.is_(True)).order_by(Stock.symbol).all()
        return [
            {
                "symbol": s.symbol,
                "name_en": s.name_en,
                "name_ar": s.name_ar,
                "sector": s.sector,
                "industry": s.industry,
                "exchange": s.exchange,
            }
            for s in rows
        ]
    finally:
        session.close()


def _max_live_snapshot_id(session_factory) -> int:
    session = session_factory()
    try:
        max_id = session.query(func.max(RecommendationSnapshot.id)).filter(
            RecommendationSnapshot.source == "live_scan"
        ).scalar()
        return max_id or 0
    finally:
        session.close()


def _snapshot_rows_since(session_factory, since_id: int) -> Dict[str, Dict[str, Any]]:
    """Real, persisted RecommendationSnapshot rows for this run, keyed
    by symbol -- the DB id / evaluated_at / provenance fields the
    outcome objects themselves don't carry."""
    session = session_factory()
    try:
        rows = (
            session.query(RecommendationSnapshot)
            .filter(RecommendationSnapshot.source == "live_scan", RecommendationSnapshot.id > since_id)
            .all()
        )
        result = {}
        for row in rows:
            result[row.symbol] = {
                "db_id": row.id,
                "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
                "engine_version": row.engine_version,
                "market_price_at_evaluation": float(row.market_price_at_evaluation) if row.market_price_at_evaluation is not None else None,
                "technical_score": float(row.technical_score) if row.technical_score is not None else None,
                "fundamental_score": float(row.fundamental_score) if row.fundamental_score is not None else None,
                "momentum_score": float(row.momentum_score) if row.momentum_score is not None else None,
                "volume_score": float(row.volume_score) if row.volume_score is not None else None,
                "risk_score": float(row.risk_score) if row.risk_score is not None else None,
                "contributor_breakdown": row.contributor_breakdown,
                "price_bar_source": row.price_bar_source,
                "price_bar_is_synthetic": row.price_bar_is_synthetic,
            }
        return result
    finally:
        session.close()


def _outcome_to_dict(outcome, snapshot_row: Optional[Dict[str, Any]], stock_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "symbol": outcome.symbol,
        "sector": outcome.sector,
        "success": outcome.success,
        "skipped_reason": outcome.skipped_reason,
        "error": outcome.error,
        "latest_price": outcome.latest_price,
        "technical_snapshot": outcome.technical_snapshot,
        "fundamental_snapshot": outcome.fundamental_snapshot,
    }
    if stock_meta:
        entry.update(
            {
                "name_en": stock_meta.get("name_en"),
                "name_ar": stock_meta.get("name_ar"),
                "industry": stock_meta.get("industry"),
                "exchange": stock_meta.get("exchange"),
            }
        )
    if outcome.report is not None:
        decision = outcome.report.decision
        explanation = outcome.report.explanation
        entry.update(
            {
                "recommendation": decision.recommendation.value if decision.recommendation else None,
                "confidence": decision.confidence,
                "final_score": decision.final_score,
                "target_price": decision.target_price,
                "stop_loss": decision.stop_loss,
                "expected_return_pct": decision.expected_return_pct,
                "time_horizon": decision.time_horizon.value if decision.time_horizon else None,
                "risk_level": decision.risk_level.value if decision.risk_level else None,
                "position_size": decision.position_size.value if decision.position_size else None,
                "entry_quality": decision.entry_quality.value if getattr(decision, "entry_quality", None) else None,
                "entry_quality_notes": getattr(decision, "entry_quality_notes", None),
                "risk_reward_ratio": getattr(decision, "risk_reward_ratio", None),
                "stop_loss_basis": getattr(decision, "stop_loss_basis", None),
                "target_price_basis": getattr(decision, "target_price_basis", None),
                "reasons": decision.reasons,
                "breakdown": [_json_default(b) for b in (decision.breakdown or [])],
                "technical_reasoning": explanation.technical_reasoning,
                "fundamental_reasoning": explanation.fundamental_reasoning,
                "risk_explanation": explanation.risk_explanation,
                "confidence_explanation": explanation.confidence_explanation,
                "target_price_explanation": explanation.target_price_explanation,
                "stop_loss_explanation": explanation.stop_loss_explanation,
                "time_horizon_explanation": explanation.time_horizon_explanation,
                "final_recommendation_rationale": explanation.final_recommendation_rationale,
                "bullish_factors": explanation.bullish_factors,
                "bearish_factors": explanation.bearish_factors,
                "alternative_scenarios": explanation.alternative_scenarios,
            }
        )
    if snapshot_row:
        entry.update(snapshot_row)
    return entry


def _ranking_lists_to_dict(rankings) -> Dict[str, Any]:
    result = {}
    for category, ranking_list in rankings.items():
        result[category.value] = [
            {
                "symbol": e.symbol, "sector": e.sector, "recommendation": e.recommendation,
                "confidence": e.confidence, "final_score": e.final_score, "target_price": e.target_price,
                "expected_return_pct": e.expected_return_pct, "risk_level": e.risk_level, "rank_value": e.rank_value,
            }
            for e in ranking_list.entries
        ]
    return result


def _watchlists_to_dict(watchlists) -> Dict[str, Any]:
    result = {}
    for category, watchlist_result in watchlists.items():
        result[category.value] = [
            {"symbol": e.symbol, "sector": e.sector, "recommendation": e.recommendation, "confidence": e.confidence, "reason": e.reason}
            for e in watchlist_result.entries
        ]
    return result


def _sector_breakdown(companies: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_sector: Dict[str, List[str]] = {}
    for c in companies:
        sector = c.get("sector") or "UNKNOWN"
        by_sector.setdefault(sector, []).append(c["symbol"])
    return {sector: {"count": len(symbols), "symbols": sorted(symbols)} for sector, symbols in sorted(by_sector.items())}


def _print_company_table(company_details: List[Dict[str, Any]]) -> None:
    """A compact, one-line-per-company table -- deliberately printed to
    stdout (not just the JSON artifact), so this data is retrievable
    even from an environment that can reach the job log API but not
    the artifact's blob-storage backend (a real, encountered
    limitation, not a hypothetical one)."""
    _section("STEP 8b: Per-company summary table (real, this scan)")
    header = (
        f"{'SYMBOL':<6} {'NAME_EN':<28} {'NAME_AR':<18} {'SECTOR':<20} {'PRICE':>10} "
        f"{'TECH':>6} {'FUND':>6} {'CONF':>6} {'REC':<11} {'TARGET':>10} {'STOP':>10} {'HORIZON':<11} {'RISK':<8}"
    )
    _print(header)
    _print("-" * len(header))
    for c in sorted(company_details, key=lambda x: x["symbol"]):
        name_en = (c.get("name_en") or "")[:28]
        name_ar = (c.get("name_ar") or "")[:18]
        sector = (c.get("sector") or "")[:20]
        price = c.get("latest_price")
        tech = c.get("technical_score")
        fund = c.get("fundamental_score")
        conf = c.get("confidence")
        rec = c.get("recommendation") or ("FAILED" if not c["success"] else "")
        target = c.get("target_price")
        stop = c.get("stop_loss")
        horizon = c.get("time_horizon") or ""
        risk = c.get("risk_level") or ""
        _print(
            f"{c['symbol']:<6} {name_en:<28} {name_ar:<18} {sector:<20} "
            f"{price if price is not None else '-':>10} "
            f"{tech if tech is not None else '-':>6} {fund if fund is not None else '-':>6} "
            f"{conf if conf is not None else '-':>6} {rec:<11} "
            f"{target if target is not None else '-':>10} {stop if stop is not None else '-':>10} "
            f"{horizon:<11} {risk:<8}"
        )
    failed = [c for c in company_details if not c["success"]]
    if failed:
        _print("\nFAILED / SKIPPED SYMBOLS (exact reasons):")
        for c in sorted(failed, key=lambda x: x["symbol"]):
            _print(f"  {c['symbol']}: skipped_reason={c.get('skipped_reason')!r} error={c.get('error')!r}")


def _print_ranking_and_watchlist_entries(rankings_dict: Dict[str, Any], watchlists_dict: Dict[str, Any]) -> None:
    """Full ranked-entry symbol lists (not just counts) -- same
    retrievability reasoning as _print_company_table."""
    _section("STEP 7b: Full ranking list contents (real, this scan)")
    for category, entries in rankings_dict.items():
        _print(f"\n[{category}] ({len(entries)} entries)")
        for e in entries:
            _print(
                f"  {e['symbol']:<6} rec={e.get('recommendation')} conf={e.get('confidence')} "
                f"score={e.get('final_score')} target={e.get('target_price')} "
                f"exp_return_pct={e.get('expected_return_pct')} risk={e.get('risk_level')} "
                f"rank_value={e.get('rank_value')}"
            )
    _section("STEP 7c: Full watchlist contents (real, this scan)")
    for category, entries in watchlists_dict.items():
        _print(f"\n[{category}] ({len(entries)} entries)")
        for e in entries:
            _print(f"  {e['symbol']:<6} rec={e.get('recommendation')} conf={e.get('confidence')} reason={e.get('reason')}")


def _write_result_artifacts(output: Dict[str, Any]) -> List[str]:
    """Task 6 of the 2026-08-02 full-market validation mandate: real,
    downloadable result artifacts, not just the existing single JSON
    blob. Best-effort against whatever `output` actually contains at
    call time -- called from every exit path (success, ValidationFailure,
    generic exception) so partial evidence is never lost to a failure
    partway through the run. Returns the list of filenames actually
    written."""
    written: List[str] = []

    def _write_csv(filename: str, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
        path = OUTPUT_DIR / filename
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})
        written.append(filename)

    def _write_json(filename: str, data: Any) -> None:
        path = OUTPUT_DIR / filename
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=_json_default, ensure_ascii=False)
        written.append(filename)

    companies: List[Dict[str, Any]] = output.get("companies") or []

    if companies:
        _write_csv(
            "full_market_results.csv",
            [
                "symbol", "name_en", "name_ar", "sector", "success", "skipped_reason", "error",
                "latest_price", "recommendation", "confidence", "target_price", "stop_loss",
                "expected_return_pct", "risk_reward_ratio", "time_horizon", "risk_level",
            ],
            companies,
        )
        _write_json("full_market_results.json", companies)

        failed_rows = [c for c in companies if not c.get("success")]
        _write_csv(
            "failed_symbols.csv",
            ["symbol", "skipped_reason", "error"],
            [
                {
                    "symbol": c.get("symbol"),
                    "skipped_reason": c.get("skipped_reason"),
                    "error": c.get("error"),
                }
                for c in failed_rows
            ],
        )

    rankings = output.get("rankings") or {}
    top_opportunities = []
    for category in ("TOP_STRONG_BUY", "TOP_BUY"):
        top_opportunities.extend(rankings.get(category, []))
    _write_json("top_opportunities.json", top_opportunities)

    classification = output.get("universe_classification") or {}
    excluded_rows = [
        {
            "symbol": c["symbol"], "name_en": c.get("name_en"), "name_ar": c.get("name_ar"),
            "bucket": c["bucket"], "exclusion_reason": c.get("exclusion_reason"),
        }
        for c in (classification.get("classifications_raw") or [])
        if not c.get("eligible", True)
    ]
    _write_csv(
        "excluded_instruments.csv", ["symbol", "name_en", "name_ar", "bucket", "exclusion_reason"], excluded_rows,
    )

    scan_summary = {
        "run_started_at": output.get("run_started_at"),
        "run_finished_at": output.get("run_finished_at"),
        "final_status": output.get("final_status"),
        "total_instruments_returned_by_sahmk": output.get("total_listed_companies_discovered"),
        "total_eligible_companies": output.get("total_eligible_companies"),
        "sahmk_directory_diagnostics": output.get("sahmk_directory_diagnostics"),
        "universe_classification": classification,
        "accounting": output.get("accounting"),
        "timings_seconds": output.get("timings_seconds"),
        "real_sahmk_api_calls_this_run": output.get("real_sahmk_api_calls_this_run"),
    }
    _write_json("scan_summary.json", scan_summary)

    report_lines = [
        "# FULL SAUDI MARKET VALIDATION REPORT",
        "",
        f"- Run started: {output.get('run_started_at')}",
        f"- Run finished: {output.get('run_finished_at')}",
        f"- Final status: {output.get('final_status')}",
        f"- Total instruments returned by SAHMK: {output.get('total_listed_companies_discovered')}",
        f"- Total eligible common-equity symbols: {output.get('total_eligible_companies')}",
        f"- Universe classification bucket counts: {classification.get('bucket_counts')}",
        f"- Accounting invariant: {output.get('accounting')}",
        f"- Real SAHMK API calls this run: {output.get('real_sahmk_api_calls_this_run')}",
        "",
        "See `full_market_results.csv`/`.json`, `top_opportunities.json`, `failed_symbols.csv`, "
        "`excluded_instruments.csv`, and `scan_summary.json` in this same artifact for full detail.",
    ]
    report_path = OUTPUT_DIR / "FULL_SAUDI_MARKET_VALIDATION_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report_lines) + "\n")
    written.append("FULL_SAUDI_MARKET_VALIDATION_REPORT.md")

    return written


async def main() -> int:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url or database_url.startswith("sqlite"):
        _print("FATAL: DATABASE_URL must point to a real PostgreSQL instance -- refusing to run against sqlite.")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)

    run_started_at = datetime.now(timezone.utc)
    timings: Dict[str, float] = {}
    step_results: Dict[str, Any] = {}
    call_counter = _RateLimiterCallCounter()

    output: Dict[str, Any] = {
        "run_started_at": run_started_at.isoformat(),
        "market_open_at_start": is_market_open(run_started_at),
        "tadawul_local_time_at_start": run_started_at.astimezone(TADAWUL_TIMEZONE).isoformat(),
    }

    try:
        _section("STEP 1: Live SAHMK provider confirmation")
        market_provider, fundamental_provider = await _require_live_providers()
        output["providers"] = {
            "market": get_last_selected_provider_kind(),
            "fundamental": get_last_selected_fundamental_provider_kind(),
        }

        _section("STEP 2: Full symbol universe discovery (real SAHMK company directory)")
        t0 = time.monotonic()
        discovery_result = await sync_symbols([], market_provider, session_factory, discover_all=True)
        timings["discovery_seconds"] = time.monotonic() - t0
        step_results["discovery"] = vars(discovery_result)
        _print(f"Discovery result: {vars(discovery_result)}")

        # Real pagination/universe-cap evidence, read directly off the
        # live SahmkMarketDataService instance rather than depending on
        # the logging pipeline above -- belt-and-suspenders after the
        # INFO-suppression gap found in the 2026-08-02 runs. `_service`
        # is a private attribute, but this script already hard-gates on
        # market_provider being the real SahmkMarketDataProvider (see
        # _require_live_providers), so this is the same module
        # boundary, not a generic-interface violation.
        sahmk_service = getattr(market_provider, "_service", None)
        directory_diagnostics = getattr(sahmk_service, "last_directory_diagnostics", None)
        if directory_diagnostics is not None:
            output["sahmk_directory_diagnostics"] = asdict(directory_diagnostics)
            _print(f"SAHMK directory diagnostics: {asdict(directory_diagnostics)}")
        else:
            output["sahmk_directory_diagnostics"] = None
            _print(
                "WARNING: no SAHMK directory diagnostics captured -- "
                "get_company_directory() either wasn't called or ran against a "
                "cached result from a prior process. Universe-cap verdict is NOT VERIFIED."
            )

        # Real eligible-universe classification (Task 2 of the
        # 2026-08-02 full-market validation mandate): every instrument
        # SAHMK's /companies/ directory returns is classified using
        # ONLY confirmed real fields (is_etf, market, market_segment,
        # security_type, status -- see universe_policy.py's docstring
        # for exactly which live runs confirmed these). Nothing is
        # guessed: an instrument whose security_type/status/segment
        # doesn't positively match a known marker is excluded into an
        # UNCLASSIFIED_* bucket with the literal observed value
        # recorded, never silently treated as eligible.
        raw_directory: List[Any] = []
        if sahmk_service is not None:
            raw_directory = await sahmk_service.get_company_directory()
        universe_classification = classify_universe(raw_directory)
        output["universe_classification"] = {
            "total_instruments_returned_by_sahmk": universe_classification.total_instruments,
            "total_eligible": universe_classification.total_eligible,
            "total_excluded": universe_classification.total_excluded,
            "bucket_counts": universe_classification.bucket_counts,
            "distinct_observed_values": universe_classification.distinct_observed_values,
            "classifications_raw": [asdict(c) for c in universe_classification.classifications],
        }
        _print(
            f"Universe classification: {universe_classification.total_instruments} instruments returned, "
            f"{universe_classification.total_eligible} eligible common equities, "
            f"buckets={universe_classification.bucket_counts}"
        )
        _print(f"Distinct observed field values: {universe_classification.distinct_observed_values}")

        companies = _all_registered_symbols(session_factory)
        eligible_set = set(universe_classification.eligible_symbols)
        # `companies`/`all_symbols` drives every downstream ingestion +
        # scan step -- restricting it to the eligible set here is what
        # makes Task 2's classification real rather than cosmetic:
        # ETFs/REITs/sukuk/suspended/unclassified instruments are never
        # ingested, scanned, or ranked as if they were common equities.
        # If classification produced nothing (e.g. the directory call
        # itself failed and raw_directory is empty), fall back to every
        # registered symbol rather than silently scanning zero symbols.
        if eligible_set:
            companies = [c for c in companies if c["symbol"] in eligible_set]
        all_symbols = [c["symbol"] for c in companies]
        output["total_listed_companies_discovered"] = universe_classification.total_instruments
        output["total_eligible_companies"] = len(all_symbols)
        _print(f"Total instruments returned by SAHMK: {universe_classification.total_instruments}")
        _print(f"Total eligible common-equity symbols proceeding to ingestion/scan: {len(all_symbols)}")

        if not all_symbols:
            raise ValidationFailure("Discovery registered zero eligible symbols -- cannot proceed.")

        _section(f"STEP 3: Historical OHLCV ingestion -- {len(all_symbols)} real symbols")
        t0 = time.monotonic()
        ohlcv_result = await ingest_historical_ohlcv(
            all_symbols, market_provider, session_factory, backfill_days=ingestion_config.get_ohlcv_backfill_days()
        )
        timings["ohlcv_ingestion_seconds"] = time.monotonic() - t0
        step_results["ohlcv_ingestion"] = vars(ohlcv_result)
        _print(f"OHLCV ingestion: {vars(ohlcv_result)}")

        _section(f"STEP 4: Fundamentals ingestion -- {len(all_symbols)} real symbols")
        t0 = time.monotonic()
        fundamentals_result = await ingest_fundamentals(
            all_symbols, fundamental_provider, session_factory, period_type=ingestion_config.get_fundamentals_period_type()
        )
        timings["fundamentals_ingestion_seconds"] = time.monotonic() - t0
        step_results["fundamentals_ingestion"] = vars(fundamentals_result)
        _print(f"Fundamentals ingestion: {vars(fundamentals_result)}")

        _section(f"STEP 5: Dividends ingestion -- {len(all_symbols)} real symbols")
        t0 = time.monotonic()
        dividends_result = await ingest_dividends(all_symbols, fundamental_provider, session_factory)
        timings["dividends_ingestion_seconds"] = time.monotonic() - t0
        step_results["dividends_ingestion"] = vars(dividends_result)
        _print(f"Dividends ingestion: {vars(dividends_result)}")

        _section("STEP 6: Full-universe market scan (real AnalystEngine -> AIDecisionEngine)")
        repository = MarketIntelligenceRepository()
        scan_engine = MarketIntelligenceEngine(session_factory, market_provider, repository=repository)

        create_session = session_factory()
        try:
            run = repository.create_scan_run(create_session, symbols_requested=len(all_symbols))
            run_id = run.id
        finally:
            create_session.close()

        baseline_max_id = _max_live_snapshot_id(session_factory)
        t0 = time.monotonic()
        # BUG FIXED (found during the 2026-08-02 live full-universe
        # validation, run 30738871790): passing symbols=None here made
        # execute_scan() ignore the 100-symbol `all_symbols` list this
        # very run just discovered and ingested, and instead re-derive
        # a *second, independently filtered* list via SymbolSelector
        # (see symbol_selector.py) -- which silently drops any symbol
        # with zero PriceBar rows, with no skipped/failed accounting
        # anywhere. Real evidence from that run: 4 of the 100 discovered
        # symbols (1263, 1295, 2210, 2315) vanished from every count --
        # not ANALYZED, not INSUFFICIENT_DATA, not FAILED, simply never
        # attempted. Passing the already-known, already-ingested
        # all_symbols list explicitly means every discovered symbol is
        # actually attempted by MarketScanner._scan_one, which already
        # produces an honest INSUFFICIENT_DATA outcome (counted in
        # symbols_skipped) for a symbol with no usable data -- silence
        # was never a data problem, it was this call passing the wrong
        # argument.
        outcomes = await scan_engine.execute_scan(run_id, symbols=all_symbols)
        timings["scan_seconds"] = time.monotonic() - t0

        get_session = session_factory()
        try:
            run = repository.get_run(get_session, run_id)
            scan_run_summary = {
                "run_id": run_id, "status": run.status.value,
                "symbols_requested": run.symbols_requested, "symbols_succeeded": run.symbols_succeeded,
                "symbols_skipped": run.symbols_skipped, "symbols_failed": run.symbols_failed,
                "duration_seconds": float(run.duration_seconds) if run.duration_seconds is not None else None,
                "error_summary": run.error_summary,
            }
        finally:
            get_session.close()
        step_results["scan_run"] = scan_run_summary
        _print(f"MarketScanRun {run_id}: {scan_run_summary}")

        # Zero-silent-loss accounting invariant (Task 3 of the
        # 2026-08-02 full-market validation mandate): every eligible
        # discovered symbol must land in exactly one terminal bucket.
        # This is the same real defect class fixed in commit 25707f0
        # (4 of 100 symbols vanished with no accounting anywhere) --
        # this check makes a recurrence of that defect, in any form,
        # an immediate hard failure instead of a silently-wrong count.
        terminal_buckets: Dict[str, List[str]] = {
            "SUCCESS": [], "FAILED": [], "SKIPPED": [], "INSUFFICIENT_DATA": [],
        }
        for o in outcomes:
            if o.success:
                terminal_buckets["SUCCESS"].append(o.symbol)
            elif o.skipped_reason == "insufficient_data":
                terminal_buckets["INSUFFICIENT_DATA"].append(o.symbol)
            elif o.error is not None:
                terminal_buckets["FAILED"].append(o.symbol)
            else:
                terminal_buckets["SKIPPED"].append(o.symbol)

        outcome_symbols = {o.symbol for o in outcomes}
        eligible_set_for_check = set(all_symbols)
        missing_entirely = sorted(eligible_set_for_check - outcome_symbols)
        terminal_total = sum(len(v) for v in terminal_buckets.values())
        output["accounting"] = {
            "eligible_discovered": len(all_symbols),
            "success": len(terminal_buckets["SUCCESS"]),
            "failed": len(terminal_buckets["FAILED"]),
            "skipped": len(terminal_buckets["SKIPPED"]),
            "insufficient_data": len(terminal_buckets["INSUFFICIENT_DATA"]),
            "terminal_total": terminal_total,
            "missing_entirely": missing_entirely,
            "balances": terminal_total == len(all_symbols) and not missing_entirely,
        }
        _print(f"Accounting invariant: {output['accounting']}")
        if missing_entirely or terminal_total != len(all_symbols):
            raise ValidationFailure(
                "ZERO_SILENT_LOSS_VIOLATION: eligible_discovered "
                f"({len(all_symbols)}) != success+failed+skipped+insufficient_data "
                f"({terminal_total}). Symbols with no terminal outcome at all: "
                f"{missing_entirely}. This is a hard failure, not a warning -- "
                "no symbol may disappear between discovery and the final report."
            )

        scan_market_open = is_market_open(datetime.now(timezone.utc))
        output["market_open_during_scan"] = scan_market_open

        _section("STEP 7: Rankings + Watchlists (real, computed from this scan's outcomes)")
        rankings = RankingEngine().rank(outcomes, change_result=None)
        watchlists = WatchlistEngine().build(outcomes)
        output["rankings"] = _ranking_lists_to_dict(rankings)
        output["watchlists"] = _watchlists_to_dict(watchlists)
        for cat, entries in output["rankings"].items():
            _print(f"  ranking[{cat}]: {len(entries)} entries")
        for cat, entries in output["watchlists"].items():
            _print(f"  watchlist[{cat}]: {len(entries)} entries")
        _print_ranking_and_watchlist_entries(output["rankings"], output["watchlists"])

        _section("STEP 8: Per-company detail dump")
        stock_by_symbol = {c["symbol"]: c for c in companies}
        snapshot_by_symbol = _snapshot_rows_since(session_factory, baseline_max_id)
        company_details = [
            _outcome_to_dict(o, snapshot_by_symbol.get(o.symbol), stock_by_symbol.get(o.symbol))
            for o in outcomes
        ]
        output["companies"] = company_details
        succeeded = [c for c in company_details if c["success"]]
        failed = [c for c in company_details if not c["success"]]
        _print(f"Scanned: {len(company_details)} | succeeded: {len(succeeded)} | failed/skipped: {len(failed)}")
        _print_company_table(company_details)

        output["sector_breakdown"] = _sector_breakdown(companies)
        output["timings_seconds"] = timings
        output["real_sahmk_api_calls_this_run"] = call_counter.count
        output["step_results"] = step_results
        output["run_finished_at"] = datetime.now(timezone.utc).isoformat()
        output["final_status"] = "MARKET_INTELLIGENCE_VERIFIED"

        data_path = OUTPUT_DIR / "market_intelligence_data.json"
        with open(data_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, default=_json_default, ensure_ascii=False)
        _print(f"\nFull data written to {data_path} ({data_path.stat().st_size} bytes)")
        artifact_files = _write_result_artifacts(output)
        _print(f"Result artifacts written: {artifact_files}")

        _section("FINAL SUMMARY")
        _print(f"Total companies discovered: {output['total_listed_companies_discovered']}")
        _print(f"Total companies scanned successfully: {len(succeeded)}")
        _print(f"Total companies failed/skipped: {len(failed)}")
        _print(f"Real SAHMK API calls made this run: {call_counter.count}")
        _print(f"Total wall-clock timings: {timings}")
        _print(f"Market open at scan time: {scan_market_open}")
        _print("FINAL_STATUS=MARKET_INTELLIGENCE_VERIFIED")

        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write("# Basirah Market Intelligence -- Full Universe Scan\n\n")
                fh.write(f"- Companies discovered: **{output['total_listed_companies_discovered']}**\n")
                fh.write(f"- Companies scanned successfully: **{len(succeeded)}**\n")
                fh.write(f"- Companies failed/skipped: **{len(failed)}**\n")
                fh.write(f"- Real SAHMK API calls: **{call_counter.count}**\n")
                fh.write(f"- Market open during scan: **{scan_market_open}**\n")
                fh.write(f"- Timings (seconds): `{timings}`\n")
                fh.write("- Full per-company data: see the `market-intelligence-data` build artifact.\n")

        return 0

    except ValidationFailure as exc:
        output["final_status"] = "ABORTED"
        output["abort_reason"] = str(exc)
        output["run_finished_at"] = datetime.now(timezone.utc).isoformat()
        _print(f"\nFINAL_STATUS=ABORTED\n{exc}")
        data_path = OUTPUT_DIR / "market_intelligence_data.json"
        with open(data_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, default=_json_default, ensure_ascii=False)
        _write_result_artifacts(output)
        return 1
    except Exception as exc:  # noqa: BLE001 -- must always write whatever partial evidence exists, never crash silently
        output["final_status"] = "FAILED"
        output["failure_reason"] = f"{type(exc).__name__}: {exc}"
        output["timings_seconds"] = timings
        output["step_results"] = step_results
        output["real_sahmk_api_calls_this_run"] = call_counter.count
        output["run_finished_at"] = datetime.now(timezone.utc).isoformat()
        _print(f"\nFINAL_STATUS=FAILED\n{type(exc).__name__}: {exc}")
        data_path = OUTPUT_DIR / "market_intelligence_data.json"
        with open(data_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, default=_json_default, ensure_ascii=False)
        _write_result_artifacts(output)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        call_counter.restore()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
