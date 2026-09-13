from pydantic import BaseModel


class PiiFieldResult(BaseModel):
    field_name: str
    masked_sample: str
    detector_type: str
    confidence: str


class PiiScanResult(BaseModel):
    scan_id: str
    fields: list[PiiFieldResult]
