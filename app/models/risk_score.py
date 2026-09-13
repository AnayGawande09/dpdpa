import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id"), nullable=False, unique=True, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(String(20), nullable=False)
    breakdown: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
