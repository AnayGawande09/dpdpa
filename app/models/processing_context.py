import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Purpose(str, enum.Enum):
    Marketing = "Marketing"
    Analytics = "Analytics"
    CustomerSupport = "Customer Support"
    LegalCompliance = "Legal/Compliance"
    Other = "Other"


class ConsentStatus(str, enum.Enum):
    Available = "Available"
    NotAvailable = "Not available"
    Unknown = "Unknown"


class RetentionUnit(str, enum.Enum):
    days = "days"
    months = "months"
    years = "years"


class NoticeStatus(str, enum.Enum):
    Available = "Available"
    Missing = "Missing"


class ProcessingContext(Base):
    __tablename__ = "processing_context"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id"), nullable=False, unique=True, index=True
    )
    purpose: Mapped[Purpose] = mapped_column(Enum(Purpose), nullable=False)
    consent_status: Mapped[ConsentStatus] = mapped_column(Enum(ConsentStatus), nullable=False)
    retention_value: Mapped[int] = mapped_column(Integer, nullable=False)
    retention_unit: Mapped[RetentionUnit] = mapped_column(Enum(RetentionUnit), nullable=False)
    access_scope: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_control_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notice_status: Mapped[NoticeStatus] = mapped_column(Enum(NoticeStatus), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
