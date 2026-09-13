from pydantic import BaseModel


class FindingResult(BaseModel):
    category: str
    affected_fields: list[str]
    purpose: str
    missing_control: str
    rule_id: str
    evidence: str
    severity: str
    explanation: str


class BreakdownItemResult(BaseModel):
    factor: str
    points_added: int
    reason: str


class RiskResult(BaseModel):
    scan_id: str
    score: int
    band: str
    breakdown: list[BreakdownItemResult]
