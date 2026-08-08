"""MarketIntelligenceEngine: the Autonomous Market Intelligence Layer's
top-level orchestrator -- select symbols, scan them, analyze sectors,
detect changes against the previous scan, generate alerts, and persist
everything via `MarketIntelligenceRepository`. Every step reuses an
already-built module (`SymbolSelector`, `MarketScanner`,
`SectorAnalyzer`, `ChangeDetector`, `AlertEngine`); this class performs
no analysis itself.
"""

import logging
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import MarketScanStatus
from src.market_data import config as market_data_config
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.strict_mode import StrictRealDataUnavailableError
from src.market_intelligence.alert_engine import AlertEngine
from src.market_intelligence.change_detector import ChangeDetector
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scanner import MarketScanner
from src.market_intelligence.sector_analysis import SectorAnalyzer
from src.market_intelligence.symbol_selector import SymbolSelector
from src.market_intelligence.types import SymbolScanOutcome

logger = logging.getLogger(__name__)


class MarketIntelligenceEngine:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        market_provider: IMarketDataProvider,
        repository: Optional[MarketIntelligenceRepository] = None,
        scanner: Optional[MarketScanner] = None,
        symbol_selector: Optional[SymbolSelector] = None,
        sector_analyzer: Optional[SectorAnalyzer] = None,
        change_detector: Optional[ChangeDetector] = None,
        alert_engine: Optional[AlertEngine] = None,
    ):
        self._session_factory = session_factory
        self._market_provider = market_provider
        self._repository = repository or MarketIntelligenceRepository()
        self._scanner = scanner or MarketScanner(session_factory, market_provider)
        self._symbol_selector = symbol_selector or SymbolSelector()
        self._sector_analyzer = sector_analyzer or SectorAnalyzer()
        self._change_detector = change_detector or ChangeDetector()
        self._alert_engine = alert_engine or AlertEngine()

    async def execute_scan(
        self,
        run_id: int,
        symbols: Optional[List[str]] = None,
        on_symbol_start: Optional[Callable[[str], None]] = None,
        on_symbol_complete: Optional[Callable[[SymbolScanOutcome], None]] = None,
        on_retry: Optional[Callable[[str, int, int, Exception], None]] = None,
    ) -> List[SymbolScanOutcome]:
        """Runs scan `run_id` (already created as a PENDING
        `MarketScanRun` row by the caller -- see
        services/scan_job_runner.py) to completion: marks it RUNNING,
        does the work, persists every result, and marks it
        SUCCESS/FAILED. Returns the scan's outcomes so a caller that
        wants them immediately (e.g. a synchronous test) doesn't have
        to re-read them back from the database.

        `on_symbol_start`/`on_symbol_complete`/`on_retry` are optional
        pass-throughs to `MarketScanner.scan()` for live progress
        reporting (see scan_progress.py) -- None by default, so every
        existing caller is unaffected.
        """
        mark_running_session = self._session_factory()
        try:
            started_at = self._repository.mark_running(mark_running_session, run_id)
        finally:
            mark_running_session.close()

        selection_session = self._session_factory()
        try:
            resolved_symbols = self._symbol_selector.select(selection_session, symbols)
        finally:
            selection_session.close()

        # Phase 3A: the previous completed run's market breadth, read
        # once per scan (not once per symbol) and handed to every
        # symbol's Decision Engine V2 computation -- the same "most
        # recent completed run" semantics /decision-v2's own
        # _latest_market_breadth already uses for a single symbol.
        # Best-effort: a missing/failed lookup degrades to None, which
        # classify_market_risk already handles honestly as
        # INSUFFICIENT_DATA rather than failing the whole scan.
        breadth_session = self._session_factory()
        try:
            latest_run = self._repository.get_latest_successful_run(breadth_session)
            market_breadth = (
                self._repository.get_market_breadth(breadth_session, latest_run.id)
                if latest_run is not None
                else None
            )
        except Exception as exc:  # noqa: BLE001 -- best-effort, matches _latest_market_breadth's pattern
            logger.info("Could not read latest market breadth for this scan's Decision V2 pass: %s", exc)
            market_breadth = None
        finally:
            breadth_session.close()

        outcomes = await self._scanner.scan(
            resolved_symbols,
            on_symbol_start=on_symbol_start,
            on_symbol_complete=on_symbol_complete,
            on_retry=on_retry,
            market_breadth=market_breadth,
        )

        try:
            # Strict real-data mode's last, defense-in-depth check
            # before anything from this run is written: provider_factory
            # already refuses to hand out a synthetic provider in
            # strict mode (so this should be structurally unreachable
            # in the normal case), but if any outcome is nonetheless
            # marked synthetic, the *entire* run must fail -- never a
            # partial persist, never a mixed real/synthetic batch
            # reaching the database or a ranking/publication decision.
            if market_data_config.is_strict_real_data_enabled():
                synthetic_symbols = [o.symbol for o in outcomes if o.is_synthetic is True]
                if synthetic_symbols:
                    preview = ", ".join(synthetic_symbols[:5])
                    more = f" (+{len(synthetic_symbols) - 5} more)" if len(synthetic_symbols) > 5 else ""
                    raise StrictRealDataUnavailableError(
                        f"Strict real-data mode: {len(synthetic_symbols)} symbol(s) produced synthetic "
                        f"data ({preview}{more}) -- refusing to persist or publish this scan run."
                    )

            write_session = self._session_factory()
            try:
                await self._repository.save_symbol_records(write_session, run_id, outcomes)

                previous_run = self._repository.get_latest_successful_run(write_session, before_run_id=run_id)
                previous_sector_scores = (
                    self._repository.get_sector_average_scores(write_session, previous_run.id)
                    if previous_run is not None
                    else {}
                )
                sector_summaries = self._sector_analyzer.analyze(outcomes, previous_sector_scores)
                self._repository.save_sector_summaries(write_session, run_id, sector_summaries)

                previous_records = (
                    self._repository.get_symbol_records_by_symbol(write_session, previous_run.id)
                    if previous_run is not None
                    else {}
                )
                change_result = self._change_detector.detect(
                    outcomes, previous_records, previous_run.id if previous_run is not None else None
                )
                self._repository.save_change_events(write_session, run_id, change_result.events)

                alerts = self._alert_engine.generate(outcomes, change_result, sector_summaries)
                self._repository.save_alerts(write_session, run_id, alerts)

                succeeded = sum(1 for o in outcomes if o.success)
                failed = sum(1 for o in outcomes if not o.success and o.error is not None)
                skipped = len(outcomes) - succeeded - failed
                skipped_symbols_summary = self._build_skipped_symbols_summary(outcomes)
                self._repository.finish_run(
                    write_session, run_id, MarketScanStatus.SUCCESS,
                    symbols_succeeded=succeeded, symbols_skipped=skipped, symbols_failed=failed,
                    started_at=started_at,
                    skipped_symbols_summary=skipped_symbols_summary,
                )
            finally:
                write_session.close()
        except Exception as exc:
            # A run already marked RUNNING (above) must never be left
            # stuck there -- every caller of execute_scan (the REST-
            # triggered scan_job_runner, the CI full-market validation
            # script) has its own top-level exception handling, but
            # neither of them re-enters here to finalize this specific
            # MarketScanRun row, so this class must guarantee mark_
            # running() and finish_run() are always paired, exactly as
            # this method's own docstring promises ("does the work,
            # persists every result, and marks it SUCCESS/FAILED").
            # Re-raised unchanged so every existing caller's own
            # handling (retry logic, CI script's FAILED/ABORTED
            # artifact) is completely unaffected.
            fail_session = self._session_factory()
            try:
                self._repository.finish_run(
                    fail_session, run_id, MarketScanStatus.FAILED,
                    symbols_succeeded=0, symbols_skipped=0, symbols_failed=0,
                    started_at=started_at,
                    error_summary=f"{type(exc).__name__}: {exc}",
                )
            finally:
                fail_session.close()
            raise

        return outcomes

    @staticmethod
    def _build_skipped_symbols_summary(outcomes: List[SymbolScanOutcome]) -> Optional[str]:
        """A "skipped" outcome (success=False, error=None, skipped_reason
        set -- e.g. "insufficient_data"/"stock_not_registered") only
        ever existed in-memory for the duration of this scan; without
        capturing it here, the exact symbol/reason pair is unrecoverable
        the moment this function returns, leaving only symbols_skipped's
        aggregate count durable. Never fabricates a reason: only real
        outcome.skipped_reason values, verbatim. None when nothing was
        skipped, so a clean run's skipped_symbols_summary stays null."""
        skipped = [o for o in outcomes if not o.success and o.error is None]
        if not skipped:
            return None
        return "; ".join(f"{o.symbol}: {o.skipped_reason or 'unknown'}" for o in skipped)
