from datetime import datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    scan_id: str
    file_path: str
    download_url: str


class AuditLogEntry(BaseModel):
    id: str
    user_id: str
    scan_id: str | None
    action: str
    details: dict
    occurred_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
