import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    affected_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    missing_control: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
