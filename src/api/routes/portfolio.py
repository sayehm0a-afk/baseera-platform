"""GET/POST /api/v1/portfolio/* -- REST layer over
src.portfolio_intelligence, following the same conventions as
src/api/routes/market.py (APIError subclasses + register_error_handlers,
GET routes that only read already-persisted state).

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
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_market_provider
from src.api.exceptions import InvalidPortfolioConfigError, NoPortfolioAnalysisError, PortfolioNotFoundError
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
from src.core.db.database import get_db
from src.domain.models import Portfolio, PortfolioAnalysisSnapshot
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.portfolio_intelligence.config import get_max_holdings_per_portfolio
from src.portfolio_intelligence.portfolio_engine import PORTFOLIO_ENGINE_VERSION, PortfolioEngine
from src.portfolio_intelligence.repository import PortfolioRepository, serialize_portfolio_analysis
from src.portfolio_intelligence.types import Holding

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

_repository = PortfolioRepository()


def _get_portfolio_or_404(session: Session, portfolio_id: int) -> Portfolio:
    portfolio = _repository.get_portfolio(session, portfolio_id)
    if portfolio is None:
        raise PortfolioNotFoundError(f"No portfolio {portfolio_id}.")
    return portfolio


def _get_latest_analysis_json(session: Session, portfolio_id: int) -> dict:
    _get_portfolio_or_404(session, portfolio_id)
    snapshot: PortfolioAnalysisSnapshot = _repository.get_latest_analysis_snapshot(session, portfolio_id)
    if snapshot is None:
        raise NoPortfolioAnalysisError(
            f"Portfolio {portfolio_id} has never been analyzed -- POST /api/v1/portfolio/analyze first."
        )
    return snapshot.analysis_json


@router.post("/analyze", response_model=PortfolioAnalysisOut)
async def analyze_portfolio(
    request: PortfolioAnalyzeRequest,
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
) -> PortfolioAnalysisOut:
    if len(request.holdings) > get_max_holdings_per_portfolio():
        raise InvalidPortfolioConfigError(
            f"Portfolio has {len(request.holdings)} holdings, above the "
            f"{get_max_holdings_per_portfolio()}-holding limit for a single POST /analyze request."
        )

    if request.portfolio_id is not None:
        portfolio = _get_portfolio_or_404(session, request.portfolio_id)
        _repository.update_cash_balance(session, portfolio.id, request.cash)
    else:
        portfolio = _repository.create_portfolio(session, request.name, request.cash)

    holdings = [Holding(symbol=h.symbol, quantity=h.quantity, average_cost=h.average_cost) for h in request.holdings]
    _repository.replace_holdings(session, portfolio.id, holdings)

    engine = PortfolioEngine(session, market_provider)
    analysis = await engine.analyze(portfolio_id=portfolio.id, name=portfolio.name, holdings=holdings, cash=request.cash)

    _repository.save_analysis_snapshot(session, portfolio.id, analysis, PORTFOLIO_ENGINE_VERSION)

    return PortfolioAnalysisOut(**serialize_portfolio_analysis(analysis))


@router.get("/{portfolio_id}", response_model=PortfolioAnalysisOut)
def get_portfolio(portfolio_id: int, session: Session = Depends(get_db)) -> PortfolioAnalysisOut:
    return PortfolioAnalysisOut(**_get_latest_analysis_json(session, portfolio_id))


@router.get("/{portfolio_id}/recommendations", response_model=PortfolioRecommendationsOut)
def get_recommendations(portfolio_id: int, session: Session = Depends(get_db)) -> PortfolioRecommendationsOut:
    return PortfolioRecommendationsOut(**_get_latest_analysis_json(session, portfolio_id)["recommendations"])


@router.get("/{portfolio_id}/risk", response_model=RiskProfileOut)
def get_risk(portfolio_id: int, session: Session = Depends(get_db)) -> RiskProfileOut:
    risk_profile = _get_latest_analysis_json(session, portfolio_id)["risk_profile"]
    correlation_matrix = risk_profile.get("correlation_matrix")
    return RiskProfileOut(
        **{**risk_profile, "correlation_matrix": CorrelationMatrixOut(**correlation_matrix) if correlation_matrix else None}
    )


@router.get("/{portfolio_id}/allocation", response_model=AllocationOut)
def get_allocation(portfolio_id: int, session: Session = Depends(get_db)) -> AllocationOut:
    return AllocationOut(**_get_latest_analysis_json(session, portfolio_id)["allocation"])


@router.get("/{portfolio_id}/diversification", response_model=DiversificationOut)
def get_diversification(portfolio_id: int, session: Session = Depends(get_db)) -> DiversificationOut:
    return DiversificationOut(**_get_latest_analysis_json(session, portfolio_id)["diversification"])


@router.get("/{portfolio_id}/rebalance", response_model=RebalancePlanOut)
def get_rebalance(portfolio_id: int, session: Session = Depends(get_db)) -> RebalancePlanOut:
    recommendations = _get_latest_analysis_json(session, portfolio_id)["recommendations"]
    return RebalancePlanOut(
        rebalance_actions=recommendations["rebalance_actions"],
        new_buy_opportunities=recommendations["new_buy_opportunities"],
    )


@router.get("/{portfolio_id}/health", response_model=HealthScoreOut)
def get_health(portfolio_id: int, session: Session = Depends(get_db)) -> HealthScoreOut:
    return HealthScoreOut(**_get_latest_analysis_json(session, portfolio_id)["health_score"])
