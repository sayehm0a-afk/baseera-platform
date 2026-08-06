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

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.ai_evolution.agents.orchestrator import AgentPanelOrchestrator
from src.ai_evolution.config import is_agent_panel_enabled, is_paper_trading_enabled
from src.ai_evolution.outcome_evaluation import create_pending_outcomes
from src.ai_evolution.paper_trading import generate_challenger_snapshot, get_latest_challenger_config
from src.analysis.decision.ai_decision_engine import CATEGORY_LABELS
from src.analysis.decision_v2.types import gates_to_dicts, sub_scores_to_dict
from src.domain.models import (
    ChangeType as DomainChangeType,
    AlertSeverity as DomainAlertSeverity,
    AlertType as DomainAlertType,
    DecisionV2Snapshot,
    MarketAlert,
    MarketChangeEvent,
    MarketScanRun,
    MarketScanStatus,
    RecommendationLabel,
    RecommendationSnapshot,
    SectorIntelligenceSummary,
    Stock,
    SymbolIntelligenceRecord,
)
from src.analysis.decision.types import DecisionFactorBreakdown
from src.analysis.recommendation.types import Signal
from src.market_intelligence.types import Alert, ChangeEvent, MarketBreadthSummary, SectorSummary, SymbolScanOutcome

logger = logging.getLogger(__name__)

# The source label written into RecommendationSnapshot.source for every
# row this repository creates -- distinguishes a live scan write from a
# backtest write (src.backtesting.engine writes "backtest" via a
# separate call site) without relying on `run_id is None` as an
# implicit, easy-to-break proxy.
_LIVE_SCAN_SOURCE = "live_scan"


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


def _serialize_signals(signals: List[Signal]) -> List[dict]:
    return [
        {
            "name": signal.name,
            "description": signal.description,
            "direction": signal.direction.value,
            "source": signal.source,
            "impact": signal.impact,
        }
        for signal in signals
    ]


def _serialize_breakdown(breakdown: List[DecisionFactorBreakdown]) -> List[dict]:
    return [
        {
            "category": item.category,
            "points": item.points,
            "weight": item.weight,
            "confidence": item.confidence,
            "available": item.available,
            "notes": item.notes,
        }
        for item in breakdown
    ]


def _f(value: Optional[float]) -> Optional[float]:
    """Coerce a numeric field to a plain Python float before it
    reaches a bulk INSERT. Technical/fundamental computations upstream
    return `numpy.float64` in places; SQLite (every test in this
    codebase) tolerates that, but SQLAlchemy 2.0's insertmanyvalues
    path against psycopg2 literal-renders RETURNING parameters and
    numpy's `__repr__` (`np.float64(1.23)`) is not valid SQL, breaking
    every multi-row scan-result insert against real Postgres. `float()`
    is a no-op for values that are already plain floats."""
    return None if value is None else float(value)


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

    def reap_stale_runs(self, session: Session, max_age_hours: float) -> List[MarketScanRun]:
        """A run that crashed or was cancelled (e.g. a killed GitHub
        Actions job) never reaches finish_run and stays PENDING/RUNNING
        forever -- with nothing to distinguish it from a genuinely
        in-progress scan, the overlap guard in POST /scan (production
        audit finding) would otherwise block every future scan
        permanently. Marks any such run older than max_age_hours as
        FAILED so a new scan can proceed. Returns the runs it reaped,
        for logging."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        candidates = (
            session.query(MarketScanRun)
            .filter(MarketScanRun.status.in_([MarketScanStatus.PENDING, MarketScanStatus.RUNNING]))
            .all()
        )
        reaped = []
        for run in candidates:
            created_at = run.created_at
            if created_at.tzinfo is None:
                # SQLite does not round-trip a timezone-aware DateTime
                # faithfully across separate queries/sessions (the same
                # pitfall mark_running's own docstring documents) --
                # created_at is always written as UTC, so a naive value
                # read back is treated as UTC rather than compared
                # against an aware "now" and raising.
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at < cutoff:
                previous_status = run.status
                run.status = MarketScanStatus.FAILED
                run.finished_at = datetime.now(timezone.utc)
                run.error_summary = (
                    f"Reaped: still {previous_status.value} after {max_age_hours:.1f}h -- "
                    "treated as crashed/cancelled, never called finish_run."
                )
                reaped.append(run)
        if reaped:
            session.commit()
        return reaped

    def get_latest_successful_run(self, session: Session, before_run_id: Optional[int] = None) -> Optional[MarketScanRun]:
        query = session.query(MarketScanRun).filter(MarketScanRun.status == MarketScanStatus.SUCCESS)
        if before_run_id is not None:
            query = query.filter(MarketScanRun.id < before_run_id)
        return query.order_by(MarketScanRun.id.desc()).first()

    # --- symbol intelligence records -----------------------------------

    async def save_symbol_records(self, session: Session, run_id: int, outcomes: List[SymbolScanOutcome]) -> None:
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
                    confidence=_f(decision.confidence),
                    final_score=_f(decision.final_score),
                    target_price=_f(decision.target_price),
                    stop_loss=_f(decision.stop_loss),
                    expected_return_pct=_f(decision.expected_return_pct),
                    risk_level=decision.risk_level.value,
                    time_horizon=decision.time_horizon.value,
                    position_size=decision.position_size.value,
                    technical_score=_f(outcome.technical_score),
                    fundamental_score=_f(outcome.fundamental_score),
                    dividend_yield=_f(outcome.dividend_yield),
                    rsi=_f(outcome.rsi),
                    adx=_f(outcome.adx),
                    latest_price=_f(outcome.latest_price),
                    bollinger_upper=_f(outcome.bollinger_upper),
                    bullish_factors=list(outcome.report.explanation.bullish_factors),
                    bearish_factors=list(outcome.report.explanation.bearish_factors),
                    evaluated_at=decision.generated_at,
                    engine_version=outcome.report.engine_version,
                )
            )
            snapshot = RecommendationSnapshot(
                run_id=None,
                stock_id=stock_id,
                symbol=outcome.symbol,
                evaluated_at=decision.generated_at,
                market_price_at_evaluation=_f(outcome.latest_price),
                recommendation=RecommendationLabel(decision.recommendation.value),
                total_score=_f(decision.final_score),
                confidence_score=_f(decision.confidence),
                technical_score=_f(outcome.technical_score),
                fundamental_score=_f(outcome.fundamental_score),
                momentum_score=_f(outcome.category_score(CATEGORY_LABELS["momentum"])),
                volume_score=_f(outcome.category_score(CATEGORY_LABELS["volume"])),
                risk_score=_f(outcome.category_score(CATEGORY_LABELS["risk"])),
                contributor_breakdown=_serialize_breakdown(decision.breakdown),
                signals=_serialize_signals(decision.signals),
                reasons=list(decision.reasons),
                target_price=_f(decision.target_price),
                stop_loss=_f(decision.stop_loss),
                expected_return_pct=_f(decision.expected_return_pct),
                time_horizon=decision.time_horizon.value,
                risk_level=decision.risk_level.value,
                position_size=decision.position_size.value,
                engine_version=outcome.report.engine_version,
                source=_LIVE_SCAN_SOURCE,
                is_paper_trade=False,
            )
            session.add(snapshot)
            # E2: issue PENDING RecommendationOutcome rows (one per
            # evaluation horizon) now, so OutcomeEvaluationScheduler has
            # known rows to score once real forward price data exists.
            create_pending_outcomes(session, snapshot)
            # E7: real multi-agent panel -- opt-in (AGENT_PANEL_ENABLED),
            # never raises (see AgentPanelOrchestrator.run_panel's own
            # docstring), commits its own work when it runs.
            if is_agent_panel_enabled():
                await AgentPanelOrchestrator().run_panel(session, snapshot, decision, outcome.symbol)
            # E8: champion/challenger paper trading -- opt-in
            # (PAPER_TRADING_ENABLED), reuses this same already-built
            # AnalysisContext (no re-fetch) to score a second, VALIDATED
            # calibration candidate, never touching the champion
            # decision or production weights (see paper_trading.py).
            if is_paper_trading_enabled() and outcome.context is not None:
                challenger_config = get_latest_challenger_config(session)
                if challenger_config is not None:
                    generate_challenger_snapshot(session, snapshot, outcome.context, challenger_config)
            # Phase 3A: this symbol's Decision Engine V2 result
            # (computed by MarketScanner alongside the V1 decision
            # above, from the same InvestmentDecision -- see
            # SymbolScanOutcome.decision_v2's docstring), persisted as
            # the same insert-only DecisionV2Snapshot audit row
            # /decision-v2 writes, with scan_run_id finally populated
            # for a scan-originated decision. `decision_v2` is None
            # whenever V2 computation itself failed for this symbol
            # (best-effort) -- guarded independently of the writes
            # above so a V2-only failure never discards this symbol's
            # V1 records already added to this same session.
            if outcome.decision_v2 is not None:
                try:
                    result = outcome.decision_v2
                    session.add(
                        DecisionV2Snapshot(
                            stock_id=stock_id,
                            symbol=result.symbol,
                            company_name_ar=result.company_name_ar,
                            company_name_en=result.company_name_en,
                            sector_ar=result.sector_ar,
                            decision=result.decision.value,
                            decision_label_ar=result.decision_label_ar,
                            confidence_score=result.confidence_score,
                            opportunity_quality_score=result.opportunity_quality_score,
                            risk_score=result.risk_score,
                            data_quality_score=result.data_quality_score,
                            data_freshness_status=result.data_freshness_status.value,
                            current_price=result.current_price,
                            entry_zone_low=result.entry_zone_low,
                            entry_zone_high=result.entry_zone_high,
                            stop_loss=result.stop_loss,
                            target_1=result.target_1,
                            target_2=result.target_2,
                            target_3=result.target_3,
                            expected_return_target_1=result.expected_return_target_1,
                            expected_return_target_2=result.expected_return_target_2,
                            downside_to_stop=result.downside_to_stop,
                            risk_reward_target_1=result.risk_reward_target_1,
                            risk_reward_target_2=result.risk_reward_target_2,
                            expected_holding_period_min_days=result.expected_holding_period_min_days,
                            expected_holding_period_max_days=result.expected_holding_period_max_days,
                            expected_holding_period_label_ar=result.expected_holding_period_label_ar,
                            horizon_type=result.horizon_type,
                            market_status=result.market_status,
                            decision_timestamp=result.decision_timestamp,
                            invalidation_conditions=result.invalidation_conditions,
                            positive_reasons=result.positive_reasons,
                            negative_reasons=result.negative_reasons,
                            warnings=result.warnings,
                            recommendation_basis=result.recommendation_basis,
                            sub_scores=sub_scores_to_dict(result.sub_scores),
                            gates=gates_to_dicts(result.gates),
                            analysis_version=result.analysis_version,
                            data_source=result.data_source,
                            is_synthetic=outcome.is_synthetic,
                            scan_run_id=run_id,
                            requested_by_user_id=None,
                        )
                    )
                except Exception:  # noqa: BLE001 -- a V2 audit-row build failure must never discard this symbol's V1 records
                    logger.exception(
                        "Failed to build DecisionV2Snapshot for '%s' during scan persist -- skipped.", outcome.symbol
                    )
        session.commit()

    def get_symbol_records_by_symbol(self, session: Session, run_id: int) -> Dict[str, SymbolIntelligenceRecord]:
        rows = session.query(SymbolIntelligenceRecord).filter_by(scan_run_id=run_id).all()
        return {row.symbol: row for row in rows}

    def get_market_breadth(self, session: Session, run_id: int) -> Optional[MarketBreadthSummary]:
        """Phase 2C: a single-round-trip aggregate (COUNT/AVG, not a
        row-by-row load) so this is cheap enough to call once per
        individual stock decision -- unlike `MarketSnapshotBuilder`,
        which loads every symbol/sector row and is only ever called
        once per market-summary page view."""
        counts = dict(
            session.query(SymbolIntelligenceRecord.recommendation, func.count(SymbolIntelligenceRecord.id))
            .filter_by(scan_run_id=run_id)
            .group_by(SymbolIntelligenceRecord.recommendation)
            .all()
        )
        symbols_scanned = sum(counts.values())
        if symbols_scanned == 0:
            return None
        avg_confidence = (
            session.query(func.avg(SymbolIntelligenceRecord.confidence)).filter_by(scan_run_id=run_id).scalar()
        )
        run = session.query(MarketScanRun).filter_by(id=run_id).one_or_none()
        return MarketBreadthSummary(
            scan_run_id=run_id,
            generated_at=run.finished_at if run and run.finished_at else datetime.now(timezone.utc),
            symbols_scanned=symbols_scanned,
            buy_count=counts.get(RecommendationLabel.BUY, 0) + counts.get(RecommendationLabel.STRONG_BUY, 0),
            sell_count=counts.get(RecommendationLabel.SELL, 0) + counts.get(RecommendationLabel.STRONG_SELL, 0),
            average_confidence=_f(avg_confidence),
        )

    # --- sector summaries -------------------------------------------------

    def save_sector_summaries(self, session: Session, run_id: int, summaries: List[SectorSummary]) -> None:
        for summary in summaries:
            session.add(
                SectorIntelligenceSummary(
                    scan_run_id=run_id,
                    sector=summary.sector,
                    symbol_count=summary.symbol_count,
                    average_confidence=_f(summary.average_confidence),
                    average_final_score=_f(summary.average_final_score),
                    average_expected_return_pct=_f(summary.average_expected_return_pct),
                    average_technical_score=_f(summary.average_technical_score),
                    average_fundamental_score=_f(summary.average_fundamental_score),
                    buy_count=summary.buy_count,
                    sell_count=summary.sell_count,
                    hold_count=summary.hold_count,
                    breadth=_f(summary.breadth),
                    momentum=_f(summary.momentum),
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
                    delta=_f(event.delta),
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
