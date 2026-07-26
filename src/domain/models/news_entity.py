"""NewsEntity: one entity a NewsEvent was recognized as being about --
a company (stock), a sector, a government body, or a market-wide
tag. One article may affect multiple companies, so this is a
many-per-event table, not a single column on NewsEvent."""

import enum

from sqlalchemy import Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.core.db.database import Base


class NewsEntityType(str, enum.Enum):
    COMPANY = "COMPANY"
    SECTOR = "SECTOR"
    MARKET_WIDE = "MARKET_WIDE"
    GOVERNMENT = "GOVERNMENT"


class NewsEntity(Base):
    __tablename__ = "news_entities"

    id = Column(Integer, primary_key=True)
    news_event_id = Column(Integer, ForeignKey("news_events.id"), nullable=False, index=True)
    entity_type = Column(Enum(NewsEntityType), nullable=False, index=True)

    # stock_id/symbol both present for COMPANY entities recognized
    # against an ingested Stock; symbol alone (stock_id null) for a
    # recognized ticker not yet in the Stock reference table.
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=True, index=True)
    symbol = Column(String(16), nullable=True, index=True)
    sector = Column(String(128), nullable=True)
    label = Column(String(255), nullable=True)  # free text, e.g. a government body's name

    news_event = relationship("NewsEvent", back_populates="entities", foreign_keys=[news_event_id])
    stock = relationship("Stock")

    def __repr__(self) -> str:
        return f"<NewsEntity id={self.id} entity_type={self.entity_type} symbol={self.symbol!r}>"
