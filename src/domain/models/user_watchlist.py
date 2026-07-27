"""UserWatchlist/UserWatchlistItem: a customer's personal list of
symbols to track. Named `UserWatchlist`, not `Watchlist` (Phase 10
plan decision 12) to avoid colliding with the existing, unrelated
market-intelligence "system watchlist" concept already exposed at
GET /api/v1/market/watchlists -- that one is algorithmically generated
market-wide, this one is a user's own hand-picked list.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class UserWatchlist(Base):
    __tablename__ = "user_watchlists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    items = relationship("UserWatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<UserWatchlist id={self.id} user_id={self.user_id} name={self.name!r}>"


class UserWatchlistItem(Base):
    __tablename__ = "user_watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "stock_id", name="uq_user_watchlist_item_stock"),)

    id = Column(Integer, primary_key=True)
    watchlist_id = Column(Integer, ForeignKey("user_watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)  # denormalized for cheap listing without a join

    added_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    watchlist = relationship("UserWatchlist", back_populates="items")

    def __repr__(self) -> str:
        return f"<UserWatchlistItem id={self.id} watchlist_id={self.watchlist_id} symbol={self.symbol!r}>"
