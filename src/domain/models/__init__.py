"""Domain models, registered against src.core.db.database.Base.

Imported here (not just defined in their own modules) so that importing
this package is enough to register every model's table on Base.metadata
-- required for Alembic autogenerate and for Base.metadata.create_all()
to see all tables.
"""

from src.domain.models.stock import Stock
from src.domain.models.price_bar import PriceBar, Timeframe
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.fundamental_snapshot import FundamentalSnapshot, PeriodType
from src.domain.models.dividend import Dividend
from src.domain.models.ingestion_run_log import IngestionRunLog, IngestionJobStatus
from src.domain.models.backtest_run import BacktestRun, BacktestRunStatus, DataProvenanceMode
from src.domain.models.recommendation_snapshot import RecommendationSnapshot, RecommendationLabel
from src.domain.models.calibration_config import CalibrationConfig, CalibrationStatus
from src.domain.models.market_scan_run import MarketScanRun, MarketScanStatus
from src.domain.models.symbol_intelligence_record import SymbolIntelligenceRecord
from src.domain.models.sector_intelligence_summary import SectorIntelligenceSummary
from src.domain.models.market_alert import MarketAlert, AlertType, AlertSeverity
from src.domain.models.market_change_event import MarketChangeEvent, ChangeType
from src.domain.models.portfolio import Portfolio
from src.domain.models.portfolio_holding import PortfolioHolding
from src.domain.models.portfolio_analysis_snapshot import PortfolioAnalysisSnapshot
from src.domain.models.user import User, StaffRole
from src.domain.models.user_session import UserSession
from src.domain.models.email_verification_token import EmailVerificationToken
from src.domain.models.password_reset_token import PasswordResetToken
from src.domain.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus

__all__ = [
    "Stock",
    "PriceBar",
    "Timeframe",
    "MarketSnapshot",
    "FundamentalSnapshot",
    "PeriodType",
    "Dividend",
    "IngestionRunLog",
    "IngestionJobStatus",
    "BacktestRun",
    "BacktestRunStatus",
    "DataProvenanceMode",
    "RecommendationSnapshot",
    "RecommendationLabel",
    "CalibrationConfig",
    "CalibrationStatus",
    "MarketScanRun",
    "MarketScanStatus",
    "SymbolIntelligenceRecord",
    "SectorIntelligenceSummary",
    "MarketAlert",
    "AlertType",
    "AlertSeverity",
    "MarketChangeEvent",
    "ChangeType",
    "Portfolio",
    "PortfolioHolding",
    "PortfolioAnalysisSnapshot",
    "User",
    "StaffRole",
    "UserSession",
    "EmailVerificationToken",
    "PasswordResetToken",
    "Subscription",
    "SubscriptionPlan",
    "SubscriptionStatus",
]
