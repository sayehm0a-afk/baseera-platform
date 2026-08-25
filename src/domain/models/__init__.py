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
from src.domain.models.recommendation_outcome import RecommendationOutcome, RecommendationOutcomeStatus
from src.domain.models.confidence_calibration_model import (
    ConfidenceCalibrationModel,
    ConfidenceCalibrationStatus,
    ConfidenceCalibrationMethod,
)
from src.domain.models.discovered_pattern import DiscoveredPattern
from src.domain.models.reflection_report import ReflectionReport
from src.domain.models.agent_opinion import AgentOpinion, AgentStance
from src.domain.models.debate_session import DebateSession
from src.domain.models.daily_intelligence_snapshot import DailyIntelligenceSnapshot
from src.domain.models.calibration_config import CalibrationConfig, CalibrationStatus
from src.domain.models.market_scan_run import MarketScanRun, MarketScanStatus
from src.domain.models.market_scan_progress import MarketScanProgress
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
from src.domain.models.invoice import Invoice, InvoiceStatus
from src.domain.models.payment import Payment, PaymentStatus
from src.domain.models.audit_log import AuditLog
from src.domain.models.feature_flag import FeatureFlag
from src.domain.models.announcement import Announcement, AnnouncementSeverity
from src.domain.models.global_setting import GlobalSetting
from src.domain.models.notification import Notification, NotificationType
from src.domain.models.user_watchlist import UserWatchlist, UserWatchlistItem
from src.domain.models.user_setting import UserSetting
from src.domain.models.feedback import Feedback, FeedbackCategory
from src.domain.models.support_ticket import SupportTicket, SupportTicketStatus
from src.domain.models.ai_request import AIRequest, AIRequestStatus
from src.domain.models.recommendation_history import RecommendationHistory
from src.domain.models.report import Report, ReportType, ReportStatus
from src.domain.models.news_event import NewsEvent, NewsCategory, SentimentLabel
from src.domain.models.news_entity import NewsEntity, NewsEntityType
from src.domain.models.news_source_reliability import NewsSourceReliability
from src.domain.models.portfolio_news_alert import PortfolioNewsAlert, PortfolioAlertType
from src.domain.models.watchlist_news_alert import WatchlistNewsAlert
from src.domain.models.decision_v2_snapshot import DecisionV2Snapshot
from src.domain.models.committee_opinion import CommitteeAgentOpinion
from src.domain.models.committee_session import CommitteeConsensus
from src.domain.models.validation_session import ValidationSession, ValidationSessionStatus
from src.domain.models.decision_v2_outcome import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    NON_RESOLVING_STATUSES,
)
from src.domain.models.radar_opportunity import RadarOpportunity
from src.domain.models.recurrent_scan_cycle import RecurrentScanCycle, RecurrentScanCycleStatus
from src.domain.models.shadow_live_signal import (
    ShadowLiveSignal,
    ShadowLifecycleResult,
    PERSISTED_LIFECYCLE_RESULTS,
)

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
    "RecommendationOutcome",
    "RecommendationOutcomeStatus",
    "ConfidenceCalibrationModel",
    "ConfidenceCalibrationStatus",
    "ConfidenceCalibrationMethod",
    "DiscoveredPattern",
    "ReflectionReport",
    "AgentOpinion",
    "AgentStance",
    "DebateSession",
    "DailyIntelligenceSnapshot",
    "CalibrationConfig",
    "CalibrationStatus",
    "MarketScanRun",
    "MarketScanProgress",
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
    "Invoice",
    "InvoiceStatus",
    "Payment",
    "PaymentStatus",
    "AuditLog",
    "FeatureFlag",
    "Announcement",
    "AnnouncementSeverity",
    "GlobalSetting",
    "Notification",
    "NotificationType",
    "UserWatchlist",
    "UserWatchlistItem",
    "UserSetting",
    "Feedback",
    "FeedbackCategory",
    "SupportTicket",
    "SupportTicketStatus",
    "AIRequest",
    "AIRequestStatus",
    "RecommendationHistory",
    "Report",
    "ReportType",
    "ReportStatus",
    "NewsEvent",
    "NewsCategory",
    "SentimentLabel",
    "NewsEntity",
    "NewsEntityType",
    "NewsSourceReliability",
    "PortfolioNewsAlert",
    "PortfolioAlertType",
    "WatchlistNewsAlert",
    "DecisionV2Snapshot",
    "CommitteeAgentOpinion",
    "CommitteeConsensus",
    "ValidationSession",
    "ValidationSessionStatus",
    "DecisionV2Outcome",
    "DecisionV2OutcomeStatus",
    "NON_RESOLVING_STATUSES",
    "RadarOpportunity",
    "RecurrentScanCycle",
    "RecurrentScanCycleStatus",
    "ShadowLiveSignal",
    "ShadowLifecycleResult",
    "PERSISTED_LIFECYCLE_RESULTS",
]
