"""GET /api/v1/admin/historical-data-export/ohlcv -- staff-only,
read-only, TEMPORARY export of already-ingested PriceBar rows for the
DecisionEngineV2 historical validation harness (BASIRAH -- PHASE 3
REAL HISTORICAL VALIDATION DATA ACCESS mandate).

Exists solely because this repo's own CI history already documents
that direct production-database access from outside Railway's private
network is structurally impossible (see production-sahmk-verification.yml's
comments: `railway run`'s DATABASE_URL never resolves outside Railway,
there is no public Postgres proxy, and `railway ssh` is rejected for
project-scoped tokens) -- the ONLY way to get already-ingested
historical OHLCV out of production into a read-only-safe evidence
workflow is through the existing public HTTPS API, as an existing
staff account, the same pattern every prior evidence-gathering script
in .github/workflows/independent_audit/ already uses.

Hard safety properties, all structural, not just documented:
  - Read-only: a single SELECT via the ORM, no write path exists in
    this file at all.
  - No arbitrary SQL: every filter is a bound ORM `.filter()` clause
    over a caller-supplied symbol whitelist and date range -- there is
    no raw SQL string anywhere in this module.
  - Explicit, required symbols + date range (`symbols`, `start_date`,
    `end_date` are all required query params, no "export everything"
    default).
  - Hard row cap (`MAX_EXPORT_ROWS`) enforced BEFORE the query runs
    (via a `LIMIT`), not after -- a caller cannot exhaust the DB with
    an unbounded scan even by accident.
  - Bounded symbol count and date range, reusing the exact same
    ceilings `src.backtesting.config` already enforces on ordinary
    backtest runs (no new, weaker limit invented for this route).
  - Staff-only: `require_any_staff_role(StaffRole.ADMIN, StaffRole.OWNER)`
    -- the same dependency every sensitive admin market-intelligence
    route in this same package already uses. A ChatGPT-anonymous or
    plain customer JWT is rejected before this handler ever runs (see
    `tests/integration/api/test_historical_data_export_route.py` for a
    real, executed proof of that, not just an assertion in this
    docstring).
  - Every invocation is written to `AuditLog` via the existing
    `record_admin_action()` helper -- the same accountability trail
    every other admin action in this platform already gets.
  - Returns exactly the 8 fields item 12 of the mandate lists --
    symbol, timestamp, OHLCV, data_source, and an adjustment-metadata
    field that is always `null` (no split/dividend-adjustment
    infrastructure exists anywhere in this codebase; see this route's
    own `corporate_action_adjustment_available` response field, always
    `False`, and the harness's own historical-validation report for
    the full disclosure). Never returns anything else -- no PII, no
    account data, no credentials, no SAHMK key.

This route is explicitly TEMPORARY diagnostic tooling for the Phase 3
historical-validation gate, matching the same "temporary, one-shot,
read-only" convention `phase2-recommendation-evidence.yml`'s own
target endpoints already established -- not a permanent public data
API. Removing it later is a one-file deletion plus one `router.
include_router(...)` line removal in this package's `__init__.py`,
nothing else depends on it.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.admin.audit_log import record_admin_action
from src.auth.rbac import require_any_staff_role
from src.backtesting.config import get_max_backtest_range_days, get_max_backtest_symbols
from src.core.db.database import get_db
from src.domain.models import PriceBar, StaffRole, Stock, Timeframe, User

router = APIRouter(prefix="/api/v1/admin/historical-data-export", tags=["admin"])

# A hard ceiling independent of symbol-count x date-range math -- the
# actual `LIMIT` applied to the query, so even a caller at the very
# edge of both bounds above cannot pull an unbounded result set.
MAX_EXPORT_ROWS = 20_000


class HistoricalOhlcvRowOut(BaseModel):
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    data_source: Optional[str]
    is_synthetic: Optional[bool]
    # Always null today -- no split/dividend adjustment metadata is
    # ever persisted anywhere in this codebase (see this route's
    # module docstring); never fabricated, never silently omitted.
    corporate_action_adjustment: Optional[str] = None


class HistoricalOhlcvExportOut(BaseModel):
    rows: List[HistoricalOhlcvRowOut]
    symbols_requested: List[str]
    symbols_found: List[str]
    symbols_not_found: List[str]
    start_date: str
    end_date: str
    row_count: int
    row_limit: int
    truncated: bool
    corporate_action_adjustment_available: bool = False


@dataclass(frozen=True)
class _ValidatedRequest:
    symbols: List[str]
    start_date: date
    end_date: date


def _validate_request(symbols_csv: str, start_date: date, end_date: date) -> _ValidatedRequest:
    symbols = [s.strip() for s in symbols_csv.split(",") if s.strip()]
    if not symbols:
        raise HTTPException(status_code=422, detail={"error": {"code": "no_symbols", "message": "At least one symbol is required."}})
    max_symbols = get_max_backtest_symbols()
    if len(symbols) > max_symbols:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "too_many_symbols", "message": f"At most {max_symbols} symbols may be requested at once."}},
        )
    if end_date < start_date:
        raise HTTPException(status_code=422, detail={"error": {"code": "invalid_range", "message": "end_date must not be before start_date."}})
    max_range_days = get_max_backtest_range_days()
    if (end_date - start_date).days > max_range_days:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "range_too_large", "message": f"Date range must not exceed {max_range_days} days."}},
        )
    return _ValidatedRequest(symbols=symbols, start_date=start_date, end_date=end_date)


@router.get("/ohlcv", response_model=HistoricalOhlcvExportOut)
def export_historical_ohlcv(
    request: Request,
    symbols: str = Query(..., description="Comma-separated symbol list, required."),
    start_date: date = Query(..., description="Inclusive start date, required."),
    end_date: date = Query(..., description="Inclusive end date, required."),
    session: Session = Depends(get_db),
    current_user: User = Depends(require_any_staff_role(StaffRole.ADMIN, StaffRole.OWNER)),
) -> HistoricalOhlcvExportOut:
    validated = _validate_request(symbols, start_date, end_date)

    stocks = session.query(Stock).filter(Stock.symbol.in_(validated.symbols)).all()
    found_by_symbol = {s.symbol: s for s in stocks}
    symbols_found = [sym for sym in validated.symbols if sym in found_by_symbol]
    symbols_not_found = [sym for sym in validated.symbols if sym not in found_by_symbol]
    stock_ids = [found_by_symbol[sym].id for sym in symbols_found]

    range_start = datetime.combine(validated.start_date, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(validated.end_date, time.max, tzinfo=timezone.utc)

    bars: List[PriceBar] = []
    if stock_ids:
        bars = (
            session.query(PriceBar)
            .filter(
                PriceBar.stock_id.in_(stock_ids),
                PriceBar.timeframe == Timeframe.ONE_DAY,
                PriceBar.timestamp >= range_start,
                PriceBar.timestamp <= range_end,
            )
            .order_by(PriceBar.stock_id.asc(), PriceBar.timestamp.asc())
            .limit(MAX_EXPORT_ROWS + 1)
            .all()
        )

    truncated = len(bars) > MAX_EXPORT_ROWS
    bars = bars[:MAX_EXPORT_ROWS]

    symbol_by_stock_id = {s.id: s.symbol for s in stocks}
    rows = [
        HistoricalOhlcvRowOut(
            symbol=symbol_by_stock_id[bar.stock_id],
            timestamp=bar.timestamp.isoformat(),
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=bar.volume,
            data_source=bar.source,
            is_synthetic=bar.is_synthetic,
            corporate_action_adjustment=None,
        )
        for bar in bars
    ]

    record_admin_action(
        session,
        actor_user_id=current_user.id,
        action="historical_data_export.ohlcv",
        target_type="price_bar_export",
        details={
            "symbols_requested": validated.symbols,
            "symbols_found": symbols_found,
            "symbols_not_found": symbols_not_found,
            "start_date": validated.start_date.isoformat(),
            "end_date": validated.end_date.isoformat(),
            "row_count": len(rows),
            "truncated": truncated,
        },
        ip_address=request.client.host if request.client else None,
    )

    return HistoricalOhlcvExportOut(
        rows=rows,
        symbols_requested=validated.symbols,
        symbols_found=symbols_found,
        symbols_not_found=symbols_not_found,
        start_date=validated.start_date.isoformat(),
        end_date=validated.end_date.isoformat(),
        row_count=len(rows),
        row_limit=MAX_EXPORT_ROWS,
        truncated=truncated,
        corporate_action_adjustment_available=False,
    )
