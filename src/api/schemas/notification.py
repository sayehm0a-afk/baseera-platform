"""Response schemas for /api/v1/notifications -- the first consumer
surface for the existing `Notification` table (previously write-only:
only `portfolio_alerts.py`/`watchlist_alerts.py` wrote rows, nothing
ever read them back)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationListOut(BaseModel):
    notifications: List[NotificationOut] = Field(default_factory=list)
    unread_count: int
