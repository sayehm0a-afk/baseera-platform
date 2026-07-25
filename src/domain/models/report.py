"""Report: the periodic-generation queue for scheduled reports
(daily/sector/monthly/quarterly) -- per-symbol AI reports and the
portfolio health report are already served live by the existing
/ai and /portfolio APIs and do NOT go through this table. `report_type`
values (Phase 10 plan decision 16) are taken directly from the Reports
screen built in Phase 9. The actual PDF/generation worker is
explicitly out of scope for this milestone -- this schema is real,
the generator is documented future work.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.sql import func

from src.core.db.database import Base


class ReportType(str, enum.Enum):
    DAILY = "DAILY"
    SECTOR = "SECTOR"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class ReportStatus(str, enum.Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    report_type = Column(Enum(ReportType), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(Enum(ReportStatus), nullable=False, default=ReportStatus.PENDING)
    file_url = Column(String(500), nullable=True)

    requested_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    generated_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Report id={self.id} user_id={self.user_id} report_type={self.report_type} status={self.status}>"
