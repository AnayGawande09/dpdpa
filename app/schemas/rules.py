from pydantic import BaseModel


class RuleEvaluationResult(BaseModel):
    rule_id: str
    category: str
    severity: str
    outcome: str
    evidence_field: str
