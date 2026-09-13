from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.rule_evaluation import RuleEvaluationRow
from app.models.user import User
from app.pipeline.rules_engine import load_rules
from app.routers.auth import get_current_user
from app.routers.ingestion import _get_dataset_or_404
from app.schemas.rules import RuleEvaluationResult

router = APIRouter(prefix="/datasets", tags=["rules"])


@router.get("/{scan_id}/rules", response_model=list[RuleEvaluationResult])
async def get_rule_evaluations(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    result = await db.execute(select(RuleEvaluationRow).where(RuleEvaluationRow.scan_id == scan_id))
    rows = result.scalars().all()
    rules_by_id = {rule["rule_id"]: rule for rule in load_rules()}
    return [
        RuleEvaluationResult(
            rule_id=r.rule_id,
            category=r.category,
            severity=r.severity,
            outcome=r.outcome,
            evidence_field=r.evidence_field,
            requirement=rules_by_id.get(r.rule_id, {}).get("requirement", ""),
            remediation=rules_by_id.get(r.rule_id, {}).get("remediation", ""),
        )
        for r in rows
    ]
