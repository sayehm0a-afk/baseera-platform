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
]
