"""M10: lifecycle for `ValidationSession` -- the explicit, bounded
grouping for one deliberate live-market validation run. Every function
here is a thin, honest wrapper: it never fabricates market context it
doesn't have, and it never lets a dry run masquerade as real evidence.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.core.config.settings import get_settings
from src.domain.models import ValidationSession, ValidationSessionStatus
from src.market_intelligence.market_status import get_market_status

logger = logging.getLogger(__name__)


def _capture_market_regime_snapshot(session: Session) -> dict:
    """Only ever real, already-computed values -- never an inferred or
    guessed market state (mandate Part I: "Do not infer unavailable
    regime data"). Missing pieces (e.g. no completed scan run yet
    today) are simply absent from the dict, not filled with a default.

    Imports MarketIntelligenceRepository locally: that module imports
    this one (to look up the active session for a scan it's about to
    persist), so a module-level import here would be circular."""
    from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository

    repository = MarketIntelligenceRepository()
    status_info = get_market_status()
    snapshot = {
        "market_status": status_info.status.value,
        "market_status_label_ar": status_info.label_ar,
        "is_trading_day": status_info.is_trading_day,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        latest_run = repository.get_latest_successful_run(session)
        if latest_run is not None:
            breadth = repository.get_market_breadth(session, latest_run.id)
            if breadth is not None:
                snapshot["latest_scan_run_id"] = breadth.scan_run_id
                snapshot["latest_scan_generated_at"] = breadth.generated_at.isoformat()
                snapshot["symbols_scanned"] = breadth.symbols_scanned
                snapshot["buy_count"] = breadth.buy_count
                snapshot["sell_count"] = breadth.sell_count
                snapshot["average_confidence"] = float(breadth.average_confidence) if breadth.average_confidence is not None else None
    except Exception as exc:  # noqa: BLE001 -- best-effort context, never blocks session creation
        logger.info("Validation session: could not capture market breadth context: %s", exc)
    return snapshot


def create_validation_session(
    session: Session,
    name: str,
    *,
    is_dry_run: bool,
    created_by_user_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> ValidationSession:
    """Opens a new session. Fails loudly (no swallowed exception) if a
    RUNNING session of the same is_dry_run kind already exists --
    concurrent overlapping sessions would make every downstream
    validation_session_id grouping ambiguous."""
    existing = (
        session.query(ValidationSession)
        .filter_by(status=ValidationSessionStatus.RUNNING, is_dry_run=is_dry_run)
        .first()
    )
    if existing is not None:
        raise ValueError(
            f"A {'dry-run' if is_dry_run else 'real'} validation session (id={existing.id}, "
            f"name={existing.name!r}) is already RUNNING -- close it before starting a new one."
        )

    settings = get_settings()
    record = ValidationSession(
        name=name,
        status=ValidationSessionStatus.RUNNING,
        is_dry_run=is_dry_run,
        started_at=datetime.now(timezone.utc),
        source_production_commit=settings.deployment_commit,
        market_regime_at_start=_capture_market_regime_snapshot(session),
        notes=notes,
        created_by_user_id=created_by_user_id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    logger.info(
        "Validation session %s opened (id=%s, is_dry_run=%s, commit=%s)",
        name, record.id, is_dry_run, settings.deployment_commit,
    )
    return record


def close_validation_session(session: Session, validation_session_id: int, *, aborted: bool = False) -> ValidationSession:
    record = session.query(ValidationSession).filter_by(id=validation_session_id).one()
    if record.status != ValidationSessionStatus.RUNNING:
        raise ValueError(f"Validation session {validation_session_id} is not RUNNING (status={record.status}).")
    record.status = ValidationSessionStatus.ABORTED if aborted else ValidationSessionStatus.CLOSED
    record.ended_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(record)
    return record


def get_active_validation_session_id(session: Session, *, is_dry_run: bool = False) -> Optional[int]:
    """Called once per scan (see market_engine.py's execute_scan) to
    determine whether this scan's Decision V2 output should be tagged
    as belonging to a real M10 session. Returns None (the overwhelming
    common case) for every routine scheduled scan run outside an
    explicitly opened session -- those rows are ordinary production
    decisions, not validation evidence, and must not be silently
    swept into a session's metrics."""
    record = (
        session.query(ValidationSession.id)
        .filter_by(status=ValidationSessionStatus.RUNNING, is_dry_run=is_dry_run)
        .first()
    )
    return record[0] if record is not None else None
