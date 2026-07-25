"""MarketIntelligenceRepository: the only module that reads/writes the
Autonomous Market Intelligence Layer's domain tables (`MarketScanRun`,
`SymbolIntelligenceRecord`, `SectorIntelligenceSummary`, `MarketAlert`,
`MarketChangeEvent`). Every engine module (scanner, ranking, watchlist,
sector_analysis, change_detector, alert_engine) works with plain
dataclasses from `types.py` and never touches a `Session` itself --
this is the one seam between that pure, testable engine layer and
persistence, the same "engines compute, a thin layer persists"
separation `src.backtesting.job_runner`/`RecommendationSnapshot`
already establish one milestone down.

Takes a plain, already-open `Session` on every call (never opens or
commits its own transaction boundary beyond what's documented per
method) -- matches every other DB-touching module in this codebase
(`ohlcv_loader.py`, `fundamental_loader.py`, the backtesting engine).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import (
    ChangeType as DomainChangeType,
    AlertSeverity as DomainAlertSeverity,
    AlertType as DomainAlertType,
    MarketAlert,
    MarketChangeEvent,
    MarketScanRun,
    MarketScanStatus,
    RecommendationLabel,
    SectorIntelligenceSummary,
    Stock,
    SymbolIntelligenceRecord,
)
from src.market_intelligence.types import Alert, ChangeEvent, SectorSummary, SymbolScanOutcome


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


class MarketIntelligenceRepository:
    # --- scan run lifecycle -------------------------------------------

    def create_scan_run(self, session: Session, symbols_requested: int) -> MarketScanRun:
        run = MarketScanRun(status=MarketScanStatus.PENDING, symbols_requested=symbols_requested)
        session.add(run)
        session.commit()
        return run

    def mark_running(self, session: Session, run_id: int) -> datetime:
        """Returns the `started_at` it just wrote -- callers must pass
        this same value back into `finish_run` rather than re-reading
        `MarketScanRun.started_at` from a later `Session`: SQLite (used
        throughout this project's tests, and possibly a deployment
        without Postgres) does not round-trip a timezone-aware
        `DateTime` faithfully across separate queries, which would
        otherwise make `finished_at - started_at` raise
        "can't subtract offset-naive and offset-aware datetimes" --
        the exact pitfall src.backtesting.job_runner's `_run_and_record`
        already avoids the same way, by keeping `started_at` a plain
        Python value end to end instead of a second DB round trip."""
        started_at = datetime.now(timezone.utc)
        session.query(MarketScanRun).filter_by(id=run_id).update(
            {"status": MarketScanStatus.RUNNING, "started_at": started_at}
        )
        session.commit()
        return started_at

    def finish_run(
        self,
        session: Session,
        run_id: int,
        status: MarketScanStatus,
        symbols_succeeded: int,
        symbols_skipped: int,
        symbols_failed: int,
        started_at: Optional[datetime] = None,
        error_summary: Optional[str] = None,
    ) -> None:
        run = session.query(MarketScanRun).filter_by(id=run_id).one()
        finished_at = datetime.now(timezone.utc)
        run.status = status
        run.symbols_succeeded = symbols_succeeded
        run.symbols_skipped = symbols_skipped
        run.symbols_failed = symbols_failed
        run.error_summary = error_summary
        run.finished_at = finished_at
        if started_at is not None:
            run.duration_seconds = round((finished_at - started_at).total_seconds(), 3)
        session.commit()

    def get_run(self, session: Session, run_id: int) -> Optional[MarketScanRun]:
        return session.query(MarketScanRun).filter_by(id=run_id).one_or_none()

    def get_latest_successful_run(self, session: Session, before_run_id: Optional[int] = None) -> Optional[MarketScanRun]:
        query = session.query(MarketScanRun).filter(MarketScanRun.status == MarketScanStatus.SUCCESS)
        if before_run_id is not None:
            query = query.filter(MarketScanRun.id < before_run_id)
        return query.order_by(MarketScanRun.id.desc()).first()

    # --- symbol intelligence records -----------------------------------

    def save_symbol_records(self, session: Session, run_id: int, outcomes: List[SymbolScanOutcome]) -> None:
        symbol_to_stock_id = {
            row.symbol: row.id
            for row in session.query(Stock.symbol, Stock.id).filter(Stock.symbol.in_([o.symbol for o in outcomes])).all()
        }
        for outcome in outcomes:
            if not _successful(outcome):
                continue
            stock_id = symbol_to_stock_id.get(outcome.symbol)
            if stock_id is None:
                continue
            decision = outcome.report.decision
            session.add(
                SymbolIntelligenceRecord(
                    scan_run_id=run_id,
                    stock_id=stock_id,
                    symbol=outcome.symbol,
                    sector=outcome.sector,
                    recommendation=RecommendationLabel(decision.recommendation.value),
                    confidence=decision.confidence,
                    final_score=decision.final_score,
                    target_price=decision.target_price,
                    stop_loss=decision.stop_loss,
                    expected_return_pct=decision.expected_return_pct,
                    risk_level=decision.risk_level.value,
                    time_horizon=decision.time_horizon.value,
                    position_size=decision.position_size.value,
                    technical_score=outcome.technical_score,
                    fundamental_score=outcome.fundamental_score,
                    dividend_yield=outcome.dividend_yield,
                    rsi=outcome.rsi,
                    adx=outcome.adx,
                    latest_price=outcome.latest_price,
                    bollinger_upper=outcome.bollinger_upper,
                    bullish_factors=list(outcome.report.explanation.bullish_factors),
                    bearish_factors=list(outcome.report.explanation.bearish_factors),
                    evaluated_at=decision.generated_at,
                    engine_version=outcome.report.engine_version,
                )
            )
        session.commit()

    def get_symbol_records_by_symbol(self, session: Session, run_id: int) -> Dict[str, SymbolIntelligenceRecord]:
        rows = session.query(SymbolIntelligenceRecord).filter_by(scan_run_id=run_id).all()
        return {row.symbol: row for row in rows}

    # --- sector summaries -------------------------------------------------

    def save_sector_summaries(self, session: Session, run_id: int, summaries: List[SectorSummary]) -> None:
        for summary in summaries:
            session.add(
                SectorIntelligenceSummary(
                    scan_run_id=run_id,
                    sector=summary.sector,
                    symbol_count=summary.symbol_count,
                    average_confidence=summary.average_confidence,
                    average_final_score=summary.average_final_score,
                    average_expected_return_pct=summary.average_expected_return_pct,
                    average_technical_score=summary.average_technical_score,
                    average_fundamental_score=summary.average_fundamental_score,
                    buy_count=summary.buy_count,
                    sell_count=summary.sell_count,
                    hold_count=summary.hold_count,
                    breadth=summary.breadth,
                    momentum=summary.momentum,
                )
            )
        session.commit()

    def get_sector_average_scores(self, session: Session, run_id: int) -> Dict[str, float]:
        rows = (
            session.query(SectorIntelligenceSummary.sector, SectorIntelligenceSummary.average_final_score)
            .filter_by(scan_run_id=run_id)
            .all()
        )
        return {sector: float(score) for sector, score in rows if score is not None}

    def get_sector_summaries(self, session: Session, run_id: int) -> List[SectorIntelligenceSummary]:
        return session.query(SectorIntelligenceSummary).filter_by(scan_run_id=run_id).order_by(
            SectorIntelligenceSummary.sector
        ).all()

    # --- alerts ------------------------------------------------------------

    def save_alerts(self, session: Session, run_id: Optional[int], alerts: List[Alert]) -> None:
        for alert in alerts:
            session.add(
                MarketAlert(
                    scan_run_id=run_id,
                    alert_type=DomainAlertType(alert.alert_type.value),
                    severity=DomainAlertSeverity(alert.severity.value),
                    symbol=alert.symbol,
                    sector=alert.sector,
                    message=alert.message,
                    generated_at=alert.generated_at,
                )
            )
        session.commit()

    def get_alerts(
        self,
        session: Session,
        limit: int,
        offset: int,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
    ) -> Tuple[int, List[MarketAlert]]:
        query = session.query(MarketAlert)
        if severity is not None:
            query = query.filter(MarketAlert.severity == DomainAlertSeverity(severity))
        if alert_type is not None:
            query = query.filter(MarketAlert.alert_type == DomainAlertType(alert_type))
        query = query.order_by(MarketAlert.generated_at.desc())
        total = query.count()
        return total, query.offset(offset).limit(limit).all()

    # --- change events -------------------------------------------------------

    def save_change_events(self, session: Session, run_id: int, events: List[ChangeEvent]) -> None:
        for event in events:
            session.add(
                MarketChangeEvent(
                    scan_run_id=run_id,
                    symbol=event.symbol,
                    change_type=DomainChangeType(event.change_type.value),
                    previous_value=event.previous_value,
                    new_value=event.new_value,
                    delta=event.delta,
                    detected_at=event.detected_at,
                )
            )
        session.commit()

    def get_change_events(
        self, session: Session, limit: int, offset: int, run_id: Optional[int] = None
    ) -> Tuple[int, List[MarketChangeEvent]]:
        query = session.query(MarketChangeEvent)
        if run_id is not None:
            query = query.filter(MarketChangeEvent.scan_run_id == run_id)
        query = query.order_by(MarketChangeEvent.detected_at.desc())
        total = query.count()
        return total, query.offset(offset).limit(limit).all()
