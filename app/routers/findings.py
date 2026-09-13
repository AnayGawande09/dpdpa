from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.finding import Finding
from app.models.risk_score import RiskScore
from app.models.user import User
from app.routers.auth import get_current_user
from app.routers.ingestion import _get_dataset_or_404
from app.schemas.findings import BreakdownItemResult, FindingResult
from app.schemas.findings import RiskResult as RiskResultSchema

router = APIRouter(prefix="/datasets", tags=["findings"])


@router.get("/{scan_id}/findings", response_model=list[FindingResult])
async def get_findings(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    result = await db.execute(select(Finding).where(Finding.scan_id == scan_id))
    rows = result.scalars().all()
    return [
        FindingResult(
            category=r.category,
            affected_fields=r.affected_fields,
            purpose=r.purpose,
            missing_control=r.missing_control,
            rule_id=r.rule_id,
            evidence=r.evidence,
            severity=r.severity,
            explanation=r.explanation,
        )
        for r in rows
    ]


@router.get("/{scan_id}/risk", response_model=RiskResultSchema)
async def get_risk(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    result = await db.execute(select(RiskScore).where(RiskScore.scan_id == scan_id))
    risk_score = result.scalar_one_or_none()
    if risk_score is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk score not yet computed for this scan")

    return RiskResultSchema(
        scan_id=scan_id,
        score=risk_score.score,
        band=risk_score.band,
        breakdown=[BreakdownItemResult(**item) for item in risk_score.breakdown],
    )
