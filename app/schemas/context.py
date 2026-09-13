from datetime import datetime

from pydantic import BaseModel

from app.models.processing_context import ConsentStatus, NoticeStatus, Purpose, RetentionUnit


class ProcessingContextIn(BaseModel):
    purpose: Purpose
    consent_status: ConsentStatus
    retention_value: int
    retention_unit: RetentionUnit
    access_scope: str
    encryption_enabled: bool
    access_control_enabled: bool
    notice_status: NoticeStatus


class ProcessingContextOut(BaseModel):
    scan_id: str
    purpose: Purpose
    consent_status: ConsentStatus
    retention_value: int
    retention_unit: RetentionUnit
    access_scope: str
    encryption_enabled: bool
    access_control_enabled: bool
    notice_status: NoticeStatus
    submitted: bool
    submitted_at: datetime | None = None

    model_config = {"from_attributes": True}


# Sensible defaults shown by the frontend / API when no context has been
# submitted yet, so a demo needs only a couple of clicks.
DEFAULT_CONTEXT = {
    "purpose": Purpose.Marketing,
    "consent_status": ConsentStatus.Unknown,
    "retention_value": 5,
    "retention_unit": RetentionUnit.years,
    "access_scope": "",
    "encryption_enabled": False,
    "access_control_enabled": False,
    "notice_status": NoticeStatus.Missing,
}
