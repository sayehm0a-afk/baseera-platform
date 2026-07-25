"""PortfolioRepository: the only module that reads/writes this layer's
domain tables (`Portfolio`, `PortfolioHolding`, `PortfolioAnalysisSnapshot`)
-- the same "engines compute, a thin layer persists" separation
`src.market_intelligence.repositories.market_intelligence_repository`
already establishes one milestone down. Every engine module in this
package works with plain `types.py` dataclasses and never touches a
`Session` itself except `RiskEngine`/`RebalanceEngine`, which read
already-ingested price/scan history through their own existing
loaders -- this repository is the one seam for this layer's own
tables.

Reuses `src.market_data.ingestion._common.get_or_create_stock` for
adding a holding whose symbol has no `Stock` row yet, rather than
duplicating that lookup-or-create logic.
"""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Portfolio, PortfolioAnalysisSnapshot, PortfolioHolding
from src.market_data.ingestion._common import get_or_create_stock
from src.portfolio_intelligence.types import Holding, HoldingAnalysis, PortfolioAnalysis


class PortfolioRepository:
    # --- portfolio lifecycle -----------------------------------------------

    def create_portfolio(
        self, session: Session, name: str, cash_balance: float, user_id: Optional[int] = None
    ) -> Portfolio:
        """`user_id` is optional here only so existing engine-level
        tests (which exercise analysis, not ownership) don't all need
        updating -- every route that creates a portfolio
        (src/api/routes/portfolio.py) always supplies it."""
        portfolio = Portfolio(name=name, cash_balance=cash_balance, user_id=user_id)
        session.add(portfolio)
        session.commit()
        return portfolio

    def get_portfolio(self, session: Session, portfolio_id: int) -> Optional[Portfolio]:
        return session.query(Portfolio).filter_by(id=portfolio_id).one_or_none()

    def get_portfolio_for_user(self, session: Session, portfolio_id: int, user_id: int) -> Optional[Portfolio]:
        """Ownership-enforced fetch for the REST layer -- returns None
        both when the portfolio doesn't exist and when it belongs to a
        different user, so a caller can never distinguish "not yours"
        from "doesn't exist" (404, not 403, in src/api/routes/portfolio.py)."""
        return session.query(Portfolio).filter_by(id=portfolio_id, user_id=user_id).one_or_none()

    def list_portfolios(self, session: Session, limit: int, offset: int) -> Tuple[int, List[Portfolio]]:
        query = session.query(Portfolio).order_by(Portfolio.id)
        total = query.count()
        return total, query.offset(offset).limit(limit).all()

    def list_portfolios_for_user(
        self, session: Session, user_id: int, limit: int, offset: int
    ) -> Tuple[int, List[Portfolio]]:
        query = session.query(Portfolio).filter_by(user_id=user_id).order_by(Portfolio.id)
        total = query.count()
        return total, query.offset(offset).limit(limit).all()

    def update_cash_balance(self, session: Session, portfolio_id: int, cash_balance: float) -> None:
        session.query(Portfolio).filter_by(id=portfolio_id).update({"cash_balance": cash_balance})
        session.commit()

    # --- holdings ------------------------------------------------------------

    def replace_holdings(self, session: Session, portfolio_id: int, holdings: List[Holding]) -> None:
        """Replaces every existing PortfolioHolding row for this
        portfolio with `holdings` -- POST /portfolio/analyze always
        submits the portfolio's complete current holdings list, never
        a partial delta, so a full replace (not an incremental upsert)
        is the correct, unambiguous semantics."""
        session.query(PortfolioHolding).filter_by(portfolio_id=portfolio_id).delete()
        for holding in holdings:
            stock = get_or_create_stock(session, holding.symbol)
            session.add(
                PortfolioHolding(
                    portfolio_id=portfolio_id, stock_id=stock.id, symbol=holding.symbol,
                    quantity=holding.quantity, average_cost=holding.average_cost,
                )
            )
        session.commit()

    def get_holdings(self, session: Session, portfolio_id: int) -> List[Holding]:
        rows = session.query(PortfolioHolding).filter_by(portfolio_id=portfolio_id).order_by(PortfolioHolding.symbol).all()
        return [
            Holding(
                symbol=row.symbol, quantity=float(row.quantity),
                average_cost=float(row.average_cost) if row.average_cost is not None else None,
            )
            for row in rows
        ]

    # --- analysis snapshots -------------------------------------------------

    def save_analysis_snapshot(
        self, session: Session, portfolio_id: int, analysis: PortfolioAnalysis, engine_version: str
    ) -> PortfolioAnalysisSnapshot:
        snapshot = PortfolioAnalysisSnapshot(
            portfolio_id=portfolio_id,
            total_value=analysis.total_value,
            cash=analysis.cash,
            health_score=analysis.health_score.score,
            risk_score=analysis.risk_profile.risk_score,
            risk_level=analysis.risk_profile.risk_level.value,
            diversification_score=analysis.diversification.score,
            expected_volatility_annualized_pct=analysis.risk_profile.expected_volatility_annualized_pct,
            estimated_max_drawdown_pct=analysis.risk_profile.estimated_max_drawdown_pct,
            portfolio_beta=analysis.risk_profile.portfolio_beta,
            analysis_json=serialize_portfolio_analysis(analysis),
            engine_version=engine_version,
            generated_at=analysis.generated_at,
        )
        session.add(snapshot)
        session.commit()
        return snapshot

    def get_latest_analysis_snapshot(self, session: Session, portfolio_id: int) -> Optional[PortfolioAnalysisSnapshot]:
        """Ordered by `id` (insertion order), not `generated_at` --
        `generated_at` is caller-supplied (from `PortfolioAnalysis.
        generated_at`) and can legitimately collide across two
        analyses of the same portfolio run in close succession, which
        would otherwise make "the latest snapshot" ambiguous."""
        return (
            session.query(PortfolioAnalysisSnapshot)
            .filter_by(portfolio_id=portfolio_id)
            .order_by(PortfolioAnalysisSnapshot.id.desc())
            .first()
        )


def _serialize_holding(holding: HoldingAnalysis) -> dict:
    return {
        "symbol": holding.symbol,
        "sector": holding.sector,
        "quantity": holding.quantity,
        "average_cost": holding.average_cost,
        "latest_price": holding.latest_price,
        "market_value": holding.market_value,
        "weight": holding.weight,
        "unrealized_pnl": holding.unrealized_pnl,
        "unrealized_pnl_pct": holding.unrealized_pnl_pct,
        "available": holding.available,
        "recommendation": holding.recommendation.value if holding.recommendation else None,
        "confidence": holding.confidence,
        "risk_level": holding.risk_level.value if holding.risk_level else None,
        "position_size": holding.position_size.value if holding.position_size else None,
        "target_price": holding.report.decision.target_price if holding.report else None,
        "error": holding.error,
    }


def serialize_portfolio_analysis(analysis: PortfolioAnalysis) -> dict:
    """Turns a `PortfolioAnalysis` into a JSON-safe dict -- the same
    "flatten enums to their string value, datetimes to ISO strings,
    reuse only summary fields (never the full nested AnalystReport
    prose)" discipline `src.market_intelligence.repositories.
    market_intelligence_repository`/`SymbolIntelligenceRecord` already
    apply one milestone down. This is the single source of truth both
    `PortfolioRepository.save_analysis_snapshot` (for durable storage)
    and the REST layer (for the POST /analyze response) read from."""
    risk = analysis.risk_profile
    return {
        "portfolio_id": analysis.portfolio_id,
        "name": analysis.name,
        "cash": analysis.cash,
        "total_value": analysis.total_value,
        "generated_at": analysis.generated_at.isoformat(),
        "holdings": [_serialize_holding(h) for h in analysis.holdings],
        "allocation": {
            "entries": [
                {"symbol": e.symbol, "sector": e.sector, "quantity": e.quantity, "market_value": e.market_value, "weight": e.weight}
                for e in analysis.allocation.entries
            ],
            "cash": analysis.allocation.cash,
            "cash_weight": analysis.allocation.cash_weight,
            "total_value": analysis.allocation.total_value,
        },
        "sector_exposure": [
            {"sector": s.sector, "market_value": s.market_value, "weight": s.weight, "holdings_count": s.holdings_count, "symbols": s.symbols}
            for s in analysis.sector_exposure
        ],
        "concentration": {
            "herfindahl_index": analysis.concentration.herfindahl_index,
            "sector_herfindahl_index": analysis.concentration.sector_herfindahl_index,
            "largest_position_symbol": analysis.concentration.largest_position_symbol,
            "largest_position_weight": analysis.concentration.largest_position_weight,
            "top_3_weight": analysis.concentration.top_3_weight,
            "is_concentrated": analysis.concentration.is_concentrated,
            "concentration_threshold": analysis.concentration.concentration_threshold,
        },
        "diversification": {
            "score": analysis.diversification.score,
            "effective_number_of_holdings": analysis.diversification.effective_number_of_holdings,
            "effective_number_of_sectors": analysis.diversification.effective_number_of_sectors,
            "sector_count": analysis.diversification.sector_count,
            "holdings_count": analysis.diversification.holdings_count,
            "narrative": analysis.diversification.narrative,
        },
        "risk_profile": {
            "risk_score": risk.risk_score,
            "risk_level": risk.risk_level.value,
            "expected_volatility_annualized_pct": risk.expected_volatility_annualized_pct,
            "estimated_max_drawdown_pct": risk.estimated_max_drawdown_pct,
            "portfolio_beta": risk.portfolio_beta,
            "beta_unavailable_reason": risk.beta_unavailable_reason,
            "correlation_matrix": (
                {
                    "symbols": risk.correlation_matrix.symbols,
                    "matrix": risk.correlation_matrix.matrix,
                    "lookback_days": risk.correlation_matrix.lookback_days,
                    "excluded_symbols": risk.correlation_matrix.excluded_symbols,
                }
                if risk.correlation_matrix is not None else None
            ),
            "excluded_from_volatility": risk.excluded_from_volatility,
            "narrative": risk.narrative,
        },
        "recommendations": {
            "rebalance_actions": [
                {
                    "symbol": a.symbol, "action": a.action.value, "current_weight": a.current_weight,
                    "rationale": a.rationale, "recommendation": a.recommendation, "confidence": a.confidence,
                }
                for a in analysis.recommendations.rebalance_actions
            ],
            "new_buy_opportunities": [
                {
                    "symbol": o.symbol, "sector": o.sector, "recommendation": o.recommendation,
                    "confidence": o.confidence, "final_score": o.final_score, "rationale": o.rationale,
                }
                for o in analysis.recommendations.new_buy_opportunities
            ],
            "cash_recommendation": {
                "current_cash": analysis.recommendations.cash_recommendation.current_cash,
                "current_cash_pct": analysis.recommendations.cash_recommendation.current_cash_pct,
                "recommended_cash_pct_min": analysis.recommendations.cash_recommendation.recommended_cash_pct_min,
                "recommended_cash_pct_max": analysis.recommendations.cash_recommendation.recommended_cash_pct_max,
                "recommended_cash_amount_min": analysis.recommendations.cash_recommendation.recommended_cash_amount_min,
                "recommended_cash_amount_max": analysis.recommendations.cash_recommendation.recommended_cash_amount_max,
                "is_within_target_band": analysis.recommendations.cash_recommendation.is_within_target_band,
                "rationale": analysis.recommendations.cash_recommendation.rationale,
            },
            "optimization_recommendations": [
                {"priority": r.priority, "title": r.title, "rationale": r.rationale}
                for r in analysis.recommendations.optimization_recommendations
            ],
        },
        "health_score": {
            "score": analysis.health_score.score,
            "band": analysis.health_score.band.value,
            "components": analysis.health_score.components,
            "narrative": analysis.health_score.narrative,
        },
    }
