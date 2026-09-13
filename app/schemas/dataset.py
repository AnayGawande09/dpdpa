from datetime import datetime

from pydantic import BaseModel

from app.models.dataset import DatasetStatus


class UploadResponse(BaseModel):
    scan_id: str
    filename: str
    row_count: int
    column_names: list[str]


class DatasetResponse(BaseModel):
    scan_id: str
    filename: str
    row_count: int
    column_names: list[str]
    status: DatasetStatus
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ScanAcceptedResponse(BaseModel):
    scan_id: str
    status: DatasetStatus
