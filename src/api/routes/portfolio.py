"""GET/POST /api/v1/portfolio/* -- REST layer over
src.portfolio_intelligence, following the same conventions as
src/api/routes/market.py (APIError subclasses + register_error_handlers,
GET routes that only read already-persisted state).

Every route requires an active subscription via `require_active_subscription()`
(Phase 10 M10.5 ownership + this fix, matching the same gate already
applied to src/api/routes/stocks.py and market.py per Phase 13 P13.5
-- previously this file only required plain authentication via
`get_current_user`, letting any registered account reach premium
portfolio-intelligence output for free; that gap is closed here) and
is scoped to that user's own portfolios -- `_get_portfolio_or_404`
looks up a portfolio filtered by owner, so requesting another user's
portfolio ID looks identical to requesting one that doesn't exist
(404, never 403): the same existence-leakage avoidance already used
for other users' UserSessions in src/api/routes/auth.py.

`POST /api/v1/portfolio/analyze` runs synchronously (no BackgroundTask,
unlike `POST /api/v1/market/scan`) -- a portfolio's holdings count is
inherently small and bounded (`PORTFOLIO_MAX_HOLDINGS`), so analyzing
it is comparable in cost to a single `/analyst-report` call repeated a
few dozen times, well within normal HTTP request latency; a background
job would be unjustified complexity for this workload size. Every read
route (`/{id}`, `/{id}/recommendations`, `/{id}/risk`, `/{id}/allocation`,
`/{id}/diversification`, `/{id}/rebalance`, `/{id}/health`) reads the
latest already-persisted `PortfolioAnalysisSnapshot` for that portfolio
-- none of them re-runs an analysis.

`POST /api/v1/portfolio/analyze` is rate-limited at 30/minute (M8
security acceptance pass), matching the precedent already set for
every other computation-triggering customer route (`/market/opportunities`
is also 30/minute -- the closest precedent, since both are the
heaviest write/compute cost in their respective files;
`/market/personal/top-opportunities`, `/stocks/{symbol}/technical`,
`/stocks/{symbol}/decision-v2` are lighter per-call reads and get
60/minute -- Phase 3H). The per-call cost bound above addresses
request *size*; this addresses request *frequency* -- an authenticated
customer looping this endpoint would otherwise incur unbounded DB
writes (a new `PortfolioAnalysisSnapshot` row per call) with no cap.
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.dependencies import get_market_provider
from src.market_data.sahmk.operation_scope import PORTFOLIO, operation_scope
from src.api.exceptions import (
    DuplicateHoldingError,
    InvalidPortfolioConfigError,
    NoPortfolioAnalysisError,
    PortfolioHoldingNotFoundError,
    PortfolioNotFoundError,
)
from src.api.middleware.rate_limiting import limiter
from src.api.schemas.auth import MessageOut
from src.api.schemas.news import PortfolioNewsAlertListOut, PortfolioNewsAlertOut
from src.api.schemas.portfolio_intelligence import (
    AllocationOut,
    CorrelationMatrixOut,
    DiversificationOut,
    HealthScoreOut,
    HoldingCreateIn,
    HoldingUpdateIn,
    PortfolioAnalysisOut,
    PortfolioAnalyzeRequest,
    PortfolioCreateIn,
    PortfolioHoldingDetailOut,
    PortfolioHoldingsOut,
    PortfolioListOut,
    PortfolioRecommendationsOut,
    PortfolioSummaryOut,
    RebalancePlanOut,
    RiskProfileOut,
)
from src.auth.rbac import require_active_subscription
from src.core.db.database import get_db
from src.domain.models import (
    DecisionV2Snapshot,
    Portfolio,
    PortfolioAnalysisSnapshot,
    PortfolioHolding,
    PortfolioNewsAlert,
    PriceBar,
    Timeframe,
    User,
)
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.news_intelligence.portfolio_alerts import PortfolioNewsAlertEngine
from src.portfolio_intelligence.config import get_max_holdings_per_portfolio
from src.portfolio_intelligence.portfolio_engine import PORTFOLIO_ENGINE_VERSION, PortfolioEngine
from src.portfolio_intelligence.repository import PortfolioRepository, serialize_portfolio_analysis
from src.portfolio_intelligence.types import Holding

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

_repository = PortfolioRepository()


def _get_portfolio_or_404(session: Session, portfolio_id: int, user_id: int) -> Portfolio:
    portfolio = _repository.get_portfolio_for_user(session, portfolio_id, user_id)
    if portfolio is None:
        raise PortfolioNotFoundError(f"No portfolio {portfolio_id}.")
    return portfolio


# --- RADAR-C Phase H: "I already own this -- what now" guidance ------------
#
# Deliberately NOT the same value as a fresh "should I buy this now"
# recommendation: an existing holder's four real options are
# احتفاظ (hold) / مراقبة (watch) / تخفيف (reduce) / خروج (exit), never
# "buy more" framed as if it were a new-entry decision. This maps
# Decision Engine V2's own `decision` value (already gate-checked,
# already evidence-backed -- src.analysis.decision_v2) onto that
# four-way holder framing; it introduces no new number or signal of
# its own, only relabels what the engine already concluded for a
# holder's context.
_HOLDER_GUIDANCE_MAP: Dict[str, tuple] = {
    "STRONG_BUY_CANDIDATE": ("HOLD", "احتفاظ"),
    "BUY_CANDIDATE": ("HOLD", "احتفاظ"),
    "WAIT_FOR_ENTRY": ("WATCH", "مراقبة"),
    "WATCH": ("WATCH", "مراقبة"),
    "HOLD": ("HOLD", "احتفاظ"),
    "REDUCE": ("REDUCE", "تخفيف"),
    "EXIT": ("EXIT", "خروج"),
    "REJECT": ("EXIT", "خروج"),
}


def _holder_guidance_from_decision(decision: str) -> Optional[tuple]:
    """Returns (code, label_ar) or None (never fabricated) for a
    decision this map has no defensible mapping for yet, e.g.
    INSUFFICIENT_DATA -- an unmapped decision must render as "no
    guidance available", not silently default to any one of the four."""
    return _HOLDER_GUIDANCE_MAP.get(decision)


def _get_latest_analysis_json(session: Session, portfolio_id: int, user_id: int) -> dict:
    _get_portfolio_or_404(session, portfolio_id, user_id)
    snapshot: PortfolioAnalysisSnapshot = _repository.get_latest_analysis_snapshot(session, portfolio_id)
    if snapshot is None:
        raise NoPortfolioAnalysisError(
            f"Portfolio {portfolio_id} has never been analyzed -- POST /api/v1/portfolio/analyze first."
        )
    return snapshot.analysis_json


def _summarize(portfolio: Portfolio, holdings_count: int) -> PortfolioSummaryOut:
    return PortfolioSummaryOut(
        id=portfolio.id, name=portfolio.name, cash_balance=float(portfolio.cash_balance),
        holdings_count=holdings_count, created_at=portfolio.created_at, updated_at=portfolio.updated_at,
    )


@router.get("", response_model=PortfolioListOut)
def list_my_portfolios(
    session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> PortfolioListOut:
    """DB-only -- reads only already-persisted `Portfolio`/`PortfolioHolding`
    rows, never a live market-data call (RADAR-C Phase H)."""
    _total, portfolios = _repository.list_portfolios_for_user(session, current_user.id, limit=100, offset=0)
    holding_rows = (
        session.query(PortfolioHolding.portfolio_id, func.count(PortfolioHolding.id))
        .filter(PortfolioHolding.portfolio_id.in_([p.id for p in portfolios]))
        .group_by(PortfolioHolding.portfolio_id)
        .all()
        if portfolios
        else []
    )
    counts = dict(holding_rows)
    return PortfolioListOut(
        portfolios=[_summarize(p, counts.get(p.id, 0)) for p in portfolios]
    )


@router.post("", response_model=PortfolioSummaryOut, status_code=status.HTTP_201_CREATED)
def create_my_portfolio(
    body: PortfolioCreateIn,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> PortfolioSummaryOut:
    """Creates an empty portfolio -- no holdings, no analysis run, no
    live market-data call. Distinct from `POST /analyze`, which
    creates-or-updates a portfolio *and* immediately runs a full paid
    analysis; this is the zero-cost "start a portfolio" action the
    Phase H holdings CRUD flow builds on."""
    portfolio = _repository.create_portfolio(session, body.name, body.cash_balance, user_id=current_user.id)
    return _summarize(portfolio, holdings_count=0)


@router.delete("/{portfolio_id}", response_model=MessageOut)
def delete_my_portfolio(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> MessageOut:
    portfolio = _get_portfolio_or_404(session, portfolio_id, current_user.id)
    _repository.delete_portfolio(session, portfolio)
    return MessageOut(message=f"تم حذف المحفظة '{portfolio.name}'.")


def _latest_price_by_stock_id(session: Session, stock_ids: List[int]) -> Dict[int, tuple]:
    """(price, as_of) per stock_id from the single most recent
    already-persisted daily `PriceBar` -- the same zero-SAHMK windowed-
    query pattern `GET /api/v1/stocks/directory` uses (Phase F)."""
    if not stock_ids:
        return {}
    ranked = (
        session.query(
            PriceBar.stock_id,
            PriceBar.close,
            PriceBar.timestamp,
            func.row_number().over(partition_by=PriceBar.stock_id, order_by=PriceBar.timestamp.desc()).label("rn"),
        )
        .filter(PriceBar.stock_id.in_(stock_ids), PriceBar.timeframe == Timeframe.ONE_DAY)
        .subquery()
    )
    rows = session.query(ranked).filter(ranked.c.rn == 1).all()
    return {row.stock_id: (float(row.close), row.timestamp) for row in rows}


def _latest_decision_by_stock_id(session: Session, stock_ids: List[int]) -> Dict[int, DecisionV2Snapshot]:
    """Most recent already-persisted `DecisionV2Snapshot` per stock_id
    -- written best-effort whenever `GET /stocks/{symbol}/decision-v2`
    computes a real decision (see that model's own docstring). Never
    triggers a new decision computation itself: a holding whose symbol
    nobody has looked up recently simply has no guidance yet, which the
    route surfaces honestly rather than silently computing one here."""
    if not stock_ids:
        return {}
    ranked_ids = (
        session.query(
            DecisionV2Snapshot.id,
            DecisionV2Snapshot.stock_id,
            func.row_number()
            .over(partition_by=DecisionV2Snapshot.stock_id, order_by=DecisionV2Snapshot.decision_timestamp.desc())
            .label("rn"),
        )
        .filter(DecisionV2Snapshot.stock_id.in_(stock_ids))
        .subquery()
    )
    latest_ids = [row.id for row in session.query(ranked_ids).filter(ranked_ids.c.rn == 1).all()]
    if not latest_ids:
        return {}
    snapshots = session.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.id.in_(latest_ids)).all()
    return {s.stock_id: s for s in snapshots}


def _holding_detail(
    holding: PortfolioHolding,
    prices: Dict[int, tuple],
    decisions: Dict[int, DecisionV2Snapshot],
) -> PortfolioHoldingDetailOut:
    stock = holding.stock
    quantity = float(holding.quantity)
    average_cost = float(holding.average_cost) if holding.average_cost is not None else None

    price_row = prices.get(holding.stock_id)
    current_price, price_as_of = price_row if price_row else (None, None)
    freshness_label_ar = "آخر جلسة" if price_row else "غير معروف"

    invested_cost = quantity * average_cost if average_cost is not None else None
    current_value = quantity * current_price if current_price is not None else None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    if invested_cost is not None and current_value is not None:
        unrealized_pnl = round(current_value - invested_cost, 4)
        if invested_cost > 0:
            unrealized_pnl_pct = round(unrealized_pnl / invested_cost * 100.0, 4)

    guidance_decision = guidance_label_ar = guidance_basis_ar = None
    guidance_confidence: Optional[float] = None
    guidance_evaluated_at: Optional[datetime] = None
    snapshot = decisions.get(holding.stock_id)
    if snapshot is not None:
        mapped = _holder_guidance_from_decision(snapshot.decision)
        if mapped is not None:
            guidance_decision, guidance_label_ar = mapped
            guidance_basis_ar = snapshot.decision_summary_ar or snapshot.recommendation_basis
            guidance_confidence = float(snapshot.confidence_score)
            guidance_evaluated_at = snapshot.decision_timestamp

    return PortfolioHoldingDetailOut(
        id=holding.id,
        symbol=holding.symbol,
        name_ar=stock.name_ar if stock else None,
        name_en=stock.name_en if stock else holding.symbol,
        sector=stock.sector if stock else None,
        quantity=quantity,
        average_cost=average_cost,
        current_price=current_price,
        price_as_of=price_as_of,
        freshness_label_ar=freshness_label_ar,
        invested_cost=round(invested_cost, 4) if invested_cost is not None else None,
        current_value=round(current_value, 4) if current_value is not None else None,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        guidance_decision=guidance_decision,
        guidance_label_ar=guidance_label_ar,
        guidance_basis_ar=guidance_basis_ar,
        guidance_confidence=guidance_confidence,
        guidance_evaluated_at=guidance_evaluated_at,
    )


@router.get("/{portfolio_id}/holdings", response_model=PortfolioHoldingsOut)
def get_portfolio_holdings(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> PortfolioHoldingsOut:
    """RADAR-C Phase H: real per-position P&L and "already own this --
    what now" guidance, computed entirely from already-persisted data
    -- zero SAHMK requests, ever (mirrors GET /api/v1/stocks/directory's
    own zero-SAHMK guarantee). Distinct from `GET /{portfolio_id}`
    (the full multi-engine `PortfolioAnalysisOut`), which only exists
    after a paid `POST /analyze` call; this route always has an answer
    for a portfolio's own holdings, even one that has never been
    analyzed."""
    portfolio = _get_portfolio_or_404(session, portfolio_id, current_user.id)
    rows = _repository.list_holding_rows(session, portfolio_id)

    stock_ids = [row.stock_id for row in rows]
    prices = _latest_price_by_stock_id(session, stock_ids)
    decisions = _latest_decision_by_stock_id(session, stock_ids)

    holdings = [_holding_detail(row, prices, decisions) for row in rows]

    total_invested_cost = sum(h.invested_cost for h in holdings if h.invested_cost is not None)
    total_current_value = sum(h.current_value for h in holdings if h.current_value is not None)
    priced_and_costed = [h for h in holdings if h.invested_cost is not None and h.current_value is not None]
    total_unrealized_pnl = (
        round(sum(h.unrealized_pnl for h in priced_and_costed), 4) if priced_and_costed else None
    )
    total_unrealized_pnl_pct = (
        round(total_unrealized_pnl / sum(h.invested_cost for h in priced_and_costed) * 100.0, 4)
        if total_unrealized_pnl is not None and sum(h.invested_cost for h in priced_and_costed) > 0
        else None
    )

    return PortfolioHoldingsOut(
        portfolio_id=portfolio.id,
        name=portfolio.name,
        cash_balance=float(portfolio.cash_balance),
        holdings=holdings,
        total_invested_cost=round(total_invested_cost, 4),
        total_current_value=round(total_current_value, 4),
        total_unrealized_pnl=total_unrealized_pnl,
        total_unrealized_pnl_pct=total_unrealized_pnl_pct,
        total_value_with_cash=round(total_current_value + float(portfolio.cash_balance), 4),
    )


@router.post("/{portfolio_id}/holdings", response_model=PortfolioHoldingDetailOut, status_code=status.HTTP_201_CREATED)
def add_portfolio_holding(
    portfolio_id: int,
    body: HoldingCreateIn,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> PortfolioHoldingDetailOut:
    _get_portfolio_or_404(session, portfolio_id, current_user.id)
    try:
        holding = _repository.add_holding(session, portfolio_id, body.symbol, body.quantity, body.average_cost)
    except IntegrityError:
        raise DuplicateHoldingError(
            f"Portfolio {portfolio_id} already holds {body.symbol.upper()} -- PATCH the existing holding instead."
        )
    prices = _latest_price_by_stock_id(session, [holding.stock_id])
    decisions = _latest_decision_by_stock_id(session, [holding.stock_id])
    return _holding_detail(holding, prices, decisions)


@router.patch("/{portfolio_id}/holdings/{holding_id}", response_model=PortfolioHoldingDetailOut)
def update_portfolio_holding(
    portfolio_id: int,
    holding_id: int,
    body: HoldingUpdateIn,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> PortfolioHoldingDetailOut:
    _get_portfolio_or_404(session, portfolio_id, current_user.id)
    holding = _repository.get_holding_for_portfolio(session, portfolio_id, holding_id)
    if holding is None:
        raise PortfolioHoldingNotFoundError(f"No holding {holding_id} in portfolio {portfolio_id}.")
    holding = _repository.update_holding(session, holding, quantity=body.quantity, average_cost=body.average_cost)
    prices = _latest_price_by_stock_id(session, [holding.stock_id])
    decisions = _latest_decision_by_stock_id(session, [holding.stock_id])
    return _holding_detail(holding, prices, decisions)


@router.delete("/{portfolio_id}/holdings/{holding_id}", response_model=MessageOut)
def delete_portfolio_holding(
    portfolio_id: int,
    holding_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> MessageOut:
    _get_portfolio_or_404(session, portfolio_id, current_user.id)
    holding = _repository.get_holding_for_portfolio(session, portfolio_id, holding_id)
    if holding is None:
        raise PortfolioHoldingNotFoundError(f"No holding {holding_id} in portfolio {portfolio_id}.")
    symbol = holding.symbol
    _repository.delete_holding(session, holding)
    return MessageOut(message=f"تمت إزالة السهم '{symbol}' من المحفظة.")


@router.post("/analyze", response_model=PortfolioAnalysisOut)
@limiter.limit("30/minute")
async def analyze_portfolio(
    request: Request,
    body: PortfolioAnalyzeRequest,
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
    current_user: User = Depends(require_active_subscription()),
) -> PortfolioAnalysisOut:
    if len(body.holdings) > get_max_holdings_per_portfolio():
        raise InvalidPortfolioConfigError(
            f"Portfolio has {len(body.holdings)} holdings, above the "
            f"{get_max_holdings_per_portfolio()}-holding limit for a single POST /analyze request."
        )

    if body.portfolio_id is not None:
        portfolio = _get_portfolio_or_404(session, body.portfolio_id, current_user.id)
        _repository.update_cash_balance(session, portfolio.id, body.cash)
    else:
        portfolio = _repository.create_portfolio(session, body.name, body.cash, user_id=current_user.id)

    holdings = [Holding(symbol=h.symbol, quantity=h.quantity, average_cost=h.average_cost) for h in body.holdings]
    _repository.replace_holdings(session, portfolio.id, holdings)

    engine = PortfolioEngine(session, market_provider)
    with operation_scope(PORTFOLIO):
        analysis = await engine.analyze(
            portfolio_id=portfolio.id, name=portfolio.name, holdings=holdings, cash=body.cash
        )

    _repository.save_analysis_snapshot(session, portfolio.id, analysis, PORTFOLIO_ENGINE_VERSION)

    return PortfolioAnalysisOut(**serialize_portfolio_analysis(analysis))


@router.get("/{portfolio_id}", response_model=PortfolioAnalysisOut)
def get_portfolio(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> PortfolioAnalysisOut:
    return PortfolioAnalysisOut(**_get_latest_analysis_json(session, portfolio_id, current_user.id))


@router.get("/{portfolio_id}/recommendations", response_model=PortfolioRecommendationsOut)
def get_recommendations(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> PortfolioRecommendationsOut:
    return PortfolioRecommendationsOut(**_get_latest_analysis_json(session, portfolio_id, current_user.id)["recommendations"])


@router.get("/{portfolio_id}/risk", response_model=RiskProfileOut)
def get_risk(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> RiskProfileOut:
    risk_profile = _get_latest_analysis_json(session, portfolio_id, current_user.id)["risk_profile"]
    correlation_matrix = risk_profile.get("correlation_matrix")
    return RiskProfileOut(
        **{**risk_profile, "correlation_matrix": CorrelationMatrixOut(**correlation_matrix) if correlation_matrix else None}
    )


@router.get("/{portfolio_id}/allocation", response_model=AllocationOut)
def get_allocation(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> AllocationOut:
    return AllocationOut(**_get_latest_analysis_json(session, portfolio_id, current_user.id)["allocation"])


@router.get("/{portfolio_id}/diversification", response_model=DiversificationOut)
def get_diversification(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> DiversificationOut:
    return DiversificationOut(**_get_latest_analysis_json(session, portfolio_id, current_user.id)["diversification"])


@router.get("/{portfolio_id}/rebalance", response_model=RebalancePlanOut)
def get_rebalance(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> RebalancePlanOut:
    recommendations = _get_latest_analysis_json(session, portfolio_id, current_user.id)["recommendations"]
    return RebalancePlanOut(
        rebalance_actions=recommendations["rebalance_actions"],
        new_buy_opportunities=recommendations["new_buy_opportunities"],
    )


@router.get("/{portfolio_id}/health", response_model=HealthScoreOut)
def get_health(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> HealthScoreOut:
    return HealthScoreOut(**_get_latest_analysis_json(session, portfolio_id, current_user.id)["health_score"])


@router.get("/{portfolio_id}/news-alerts", response_model=PortfolioNewsAlertListOut)
def get_news_alerts(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> PortfolioNewsAlertListOut:
    """Already-persisted alerts -- see `POST .../news-alerts/refresh`
    to generate new ones from the latest news."""
    _get_portfolio_or_404(session, portfolio_id, current_user.id)
    rows = (
        session.query(PortfolioNewsAlert)
        .filter_by(portfolio_id=portfolio_id)
        .order_by(PortfolioNewsAlert.generated_at.desc())
        .all()
    )
    return PortfolioNewsAlertListOut(
        alerts=[
            PortfolioNewsAlertOut(
                id=a.id, portfolio_id=a.portfolio_id, symbol=a.symbol, news_event_id=a.news_event_id,
                alert_type=a.alert_type.value, severity=a.severity.value, message=a.message,
                generated_at=a.generated_at, acknowledged_at=a.acknowledged_at,
            )
            for a in rows
        ]
    )


@router.post("/{portfolio_id}/news-alerts/refresh", response_model=PortfolioNewsAlertListOut)
def refresh_news_alerts(
    portfolio_id: int, session: Session = Depends(get_db), current_user: User = Depends(require_active_subscription())
) -> PortfolioNewsAlertListOut:
    """Re-evaluates this portfolio's held positions against the latest
    analyzed news (requirement 10: "portfolio positions must be
    re-evaluated automatically when critical news arrives") and
    persists any new Upgrade/Downgrade/High Risk/Major Opportunity
    alerts -- idempotent, never duplicates an alert already generated
    for the same (portfolio, news event) pair. Does not itself collect
    new news -- pair with `POST /api/v1/news/refresh` (or a scheduled
    job calling both) to pick up genuinely new articles first."""
    portfolio = _get_portfolio_or_404(session, portfolio_id, current_user.id)
    holdings = _repository.get_holdings(session, portfolio_id)
    symbols = [h.symbol for h in holdings]

    alerts = PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, symbols)
    return PortfolioNewsAlertListOut(
        alerts=[
            PortfolioNewsAlertOut(
                id=a.id, portfolio_id=a.portfolio_id, symbol=a.symbol, news_event_id=a.news_event_id,
                alert_type=a.alert_type.value, severity=a.severity.value, message=a.message,
                generated_at=a.generated_at, acknowledged_at=None,
            )
            for a in alerts
        ]
    )
