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

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.dependencies import get_market_provider
from src.market_data.sahmk.operation_scope import PORTFOLIO, operation_scope
from src.api.exceptions import InvalidPortfolioConfigError, NoPortfolioAnalysisError, PortfolioNotFoundError
from src.api.middleware.rate_limiting import limiter
from src.api.schemas.news import PortfolioNewsAlertListOut, PortfolioNewsAlertOut
from src.api.schemas.portfolio_intelligence import (
    AllocationOut,
    CorrelationMatrixOut,
    DiversificationOut,
    HealthScoreOut,
    PortfolioAnalysisOut,
    PortfolioAnalyzeRequest,
    PortfolioRecommendationsOut,
    RebalancePlanOut,
    RiskProfileOut,
)
from src.auth.rbac import require_active_subscription
from src.core.db.database import get_db
from src.domain.models import Portfolio, PortfolioAnalysisSnapshot, PortfolioNewsAlert, User
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


def _get_latest_analysis_json(session: Session, portfolio_id: int, user_id: int) -> dict:
    _get_portfolio_or_404(session, portfolio_id, user_id)
    snapshot: PortfolioAnalysisSnapshot = _repository.get_latest_analysis_snapshot(session, portfolio_id)
    if snapshot is None:
        raise NoPortfolioAnalysisError(
            f"Portfolio {portfolio_id} has never been analyzed -- POST /api/v1/portfolio/analyze first."
        )
    return snapshot.analysis_json


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
