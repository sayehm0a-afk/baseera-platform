"""Domain models, registered against src.core.db.database.Base.

Imported here (not just defined in their own modules) so that importing
this package is enough to register every model's table on Base.metadata
-- required for Alembic autogenerate and for Base.metadata.create_all()
to see all tables.
"""

from src.domain.models.stock import Stock
from src.domain.models.price_bar import PriceBar, Timeframe
from src.domain.models.market_snapshot import MarketSnapshot

__all__ = [
    "Stock",
    "PriceBar",
    "Timeframe",
    "MarketSnapshot",
]
