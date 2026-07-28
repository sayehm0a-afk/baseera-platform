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
from src.market_data.providers.market_data_provider import IMarketDataProvider
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

    async def execute_scan(self, run_id: int, symbols: Optional[List[str]] = None) -> List[SymbolScanOutcome]:
        """Runs scan `run_id` (already created as a PENDING
        `MarketScanRun` row by the caller -- see
        services/scan_job_runner.py) to completion: marks it RUNNING,
        does the work, persists every result, and marks it
        SUCCESS/FAILED. Returns the scan's outcomes so a caller that
        wants them immediately (e.g. a synchronous test) doesn't have
        to re-read them back from the database.
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

        outcomes = await self._scanner.scan(resolved_symbols)

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
            self._repository.finish_run(
                write_session, run_id, MarketScanStatus.SUCCESS,
                symbols_succeeded=succeeded, symbols_skipped=skipped, symbols_failed=failed,
                started_at=started_at,
            )
        finally:
            write_session.close()

        return outcomes
