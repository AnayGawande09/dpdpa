import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DetectorType(str, enum.Enum):
    regex_email = "regex_email"
    regex_phone = "regex_phone"
    regex_aadhaar = "regex_aadhaar"
    regex_pan = "regex_pan"
    regex_ip = "regex_ip"
    spacy_person = "spacy_person"
    spacy_location = "spacy_location"
    column_heuristic = "column_heuristic"


class Confidence(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PiiDetection(Base):
    __tablename__ = "pii_detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    masked_sample: Mapped[str] = mapped_column(String(500), nullable=False)
    detector_type: Mapped[DetectorType] = mapped_column(Enum(DetectorType), nullable=False)
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), nullable=False)
    row_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
