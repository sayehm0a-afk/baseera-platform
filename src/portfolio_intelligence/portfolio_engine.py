"""PortfolioEngine: the Autonomous Portfolio Intelligence Layer's
top-level orchestrator.

`HoldingAnalyzer` runs the exact same reused pipeline
`src.market_intelligence.scanner.MarketScanner` uses for a market-wide
scan (`build_analysis_context` -> `AnalystEngine.analyze()`, which
itself already calls `AIDecisionEngine` -> `RecommendationEngine` ->
`TechnicalAnalysisEngine`/`FundamentalAnalysisEngine`, unmodified),
scoped to one portfolio's held symbols instead of the whole market.
No score, target, or narrative is computed in this package.

`PortfolioEngine.analyze()` wires `HoldingAnalyzer`'s output through
every portfolio-level engine (`AllocationEngine`, `ExposureEngine`,
`DiversificationEngine`, `RiskEngine`, `CashManager`, `RebalanceEngine`,
`PortfolioScore`, `RecommendationBuilder`) into one `PortfolioAnalysis`.
"""

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.analysis.analyst.analyst_engine import AnalystEngine
from src.analysis.context_builder import build_analysis_context
from src.domain.models import PeriodType, Stock
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.portfolio_intelligence.allocation_engine import AllocationEngine
from src.portfolio_intelligence.cash_manager import CashManager
from src.portfolio_intelligence.diversification_engine import DiversificationEngine
from src.portfolio_intelligence.exposure_engine import ExposureEngine
from src.portfolio_intelligence.optimization_engine import OptimizationEngine
from src.portfolio_intelligence.portfolio_score import PortfolioScore
from src.portfolio_intelligence.rebalance_engine import RebalanceEngine
from src.portfolio_intelligence.recommendation_builder import RecommendationBuilder
from src.portfolio_intelligence.risk_engine import RiskEngine
from src.portfolio_intelligence.types import Holding, HoldingAnalysis, PortfolioAnalysis

logger = logging.getLogger(__name__)

# Recorded on every PortfolioAnalysisSnapshot -- bump this when a
# change to this module or any sub-engine would make an old snapshot's
# numbers no longer reproducible from its stored inputs, the same
# discipline AIDecisionEngine.ENGINE_VERSION/ANALYST_ENGINE_VERSION
# already apply one and two layers down.
PORTFOLIO_ENGINE_VERSION = "1.0.0"


class HoldingAnalyzer:
    def __init__(
        self,
        session: Session,
        market_provider: IMarketDataProvider,
        analyst_engine: Optional[AnalystEngine] = None,
        period_type: PeriodType = PeriodType.ANNUAL,
    ):
        self._session = session
        self._market_provider = market_provider
        self._analyst_engine = analyst_engine or AnalystEngine()
        self._period_type = period_type

    async def analyze(self, holdings: List[Holding]) -> List[HoldingAnalysis]:
        return [await self._analyze_one(holding) for holding in holdings]

    async def _analyze_one(self, holding: Holding) -> HoldingAnalysis:
        stock = self._session.query(Stock).filter(Stock.symbol == holding.symbol).one_or_none()
        if stock is None:
            return self._unavailable(holding, error="symbol not registered")

        try:
            context = await build_analysis_context(stock, self._period_type, self._session, self._market_provider)
        except Exception as exc:  # noqa: BLE001 -- deliberate: one holding's failure must never abort the whole portfolio analysis.
            logger.error("Portfolio holding analysis failed for '%s': %s", holding.symbol, exc, exc_info=True)
            return self._unavailable(holding, sector=stock.sector, error=str(exc))

        if context.technical_result is None and context.fundamental_result is None:
            return self._unavailable(holding, sector=stock.sector, error=None)

        try:
            report = await self._analyst_engine.analyze(context)
        except Exception as exc:  # noqa: BLE001 -- see above.
            logger.error("AnalystEngine failed for holding '%s': %s", holding.symbol, exc, exc_info=True)
            return self._unavailable(holding, sector=stock.sector, error=str(exc))

        latest_price = context.latest_price
        market_value = holding.quantity * latest_price if latest_price is not None else None
        unrealized_pnl = None
        unrealized_pnl_pct = None
        if market_value is not None and holding.average_cost is not None:
            cost_basis = holding.quantity * holding.average_cost
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100.0) if cost_basis > 0 else None

        return HoldingAnalysis(
            symbol=holding.symbol,
            sector=stock.sector,
            quantity=holding.quantity,
            average_cost=holding.average_cost,
            latest_price=latest_price,
            market_value=market_value,
            weight=None,  # filled in by PortfolioEngine once total_value is known
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            report=report,
        )

    @staticmethod
    def _unavailable(holding: Holding, sector: Optional[str] = None, error: Optional[str] = None) -> HoldingAnalysis:
        return HoldingAnalysis(
            symbol=holding.symbol, sector=sector, quantity=holding.quantity, average_cost=holding.average_cost,
            latest_price=None, market_value=None, weight=None, unrealized_pnl=None, unrealized_pnl_pct=None,
            report=None, error=error,
        )


class PortfolioEngine:
    def __init__(
        self,
        session: Session,
        market_provider: IMarketDataProvider,
        holding_analyzer: Optional[HoldingAnalyzer] = None,
        allocation_engine: Optional[AllocationEngine] = None,
        exposure_engine: Optional[ExposureEngine] = None,
        diversification_engine: Optional[DiversificationEngine] = None,
        risk_engine: Optional[RiskEngine] = None,
        cash_manager: Optional[CashManager] = None,
        rebalance_engine: Optional[RebalanceEngine] = None,
        optimization_engine: Optional[OptimizationEngine] = None,
        portfolio_score: Optional[PortfolioScore] = None,
        recommendation_builder: Optional[RecommendationBuilder] = None,
        session_factory: Optional[Callable[[], Session]] = None,
    ):
        self._session = session
        self._holding_analyzer = holding_analyzer or HoldingAnalyzer(session, market_provider)
        self._allocation_engine = allocation_engine or AllocationEngine()
        self._exposure_engine = exposure_engine or ExposureEngine()
        self._diversification_engine = diversification_engine or DiversificationEngine()
        self._risk_engine = risk_engine or RiskEngine(session_factory or (lambda: session))
        self._cash_manager = cash_manager or CashManager()
        self._rebalance_engine = rebalance_engine or RebalanceEngine(session)
        self._optimization_engine = optimization_engine or OptimizationEngine()
        self._portfolio_score = portfolio_score or PortfolioScore()
        self._recommendation_builder = recommendation_builder or RecommendationBuilder()

    async def analyze(self, portfolio_id: int, name: str, holdings: List[Holding], cash: float) -> PortfolioAnalysis:
        raw_holdings = await self._holding_analyzer.analyze(holdings)

        allocation = self._allocation_engine.compute(raw_holdings, cash)
        weight_by_symbol = {e.symbol: e.weight for e in allocation.entries}
        holdings_with_weight = [
            dataclasses.replace(h, weight=weight_by_symbol.get(h.symbol)) for h in raw_holdings
        ]

        sector_exposure = self._exposure_engine.compute(holdings_with_weight, allocation.total_value)
        diversification, concentration = self._diversification_engine.compute(holdings_with_weight, sector_exposure)
        risk_profile = self._risk_engine.compute(holdings_with_weight)
        cash_recommendation = self._cash_manager.recommend(allocation, risk_profile)
        rebalance_plan = self._rebalance_engine.plan(holdings_with_weight, risk_profile, sector_exposure)
        health_score = self._portfolio_score.compute(diversification, risk_profile, cash_recommendation, holdings_with_weight)
        optimization_recommendations = self._optimization_engine.build(
            concentration, diversification, risk_profile, cash_recommendation, rebalance_plan
        )
        recommendations = self._recommendation_builder.build(rebalance_plan, cash_recommendation, optimization_recommendations)

        return PortfolioAnalysis(
            portfolio_id=portfolio_id,
            name=name,
            holdings=holdings_with_weight,
            cash=cash,
            total_value=allocation.total_value,
            allocation=allocation,
            sector_exposure=sector_exposure,
            concentration=concentration,
            diversification=diversification,
            risk_profile=risk_profile,
            recommendations=recommendations,
            health_score=health_score,
            generated_at=datetime.now(timezone.utc),
        )
