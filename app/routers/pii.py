from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.pii_classification import PiiClassification
from app.models.pii_detection import PiiDetection
from app.models.user import User
from app.routers.auth import get_current_user
from app.routers.ingestion import _get_dataset_or_404
from app.schemas.classification import CategorySummary
from app.schemas.pii import PiiFieldResult, PiiScanResult

router = APIRouter(prefix="/datasets", tags=["pii"])


@router.get("/{scan_id}/pii", response_model=PiiScanResult)
async def get_pii_results(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    result = await db.execute(select(PiiDetection).where(PiiDetection.scan_id == scan_id))
    detections = result.scalars().all()
    fields = [
        PiiFieldResult(
            field_name=d.field_name,
            masked_sample=d.masked_sample,
            detector_type=d.detector_type.value,
            confidence=d.confidence.value,
        )
        for d in detections
    ]
    return PiiScanResult(scan_id=scan_id, fields=fields)


@router.get("/{scan_id}/pii/summary", response_model=list[CategorySummary])
async def get_pii_summary(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    result = await db.execute(
        select(PiiClassification, PiiDetection)
        .join(PiiDetection, PiiClassification.detection_id == PiiDetection.id)
        .where(PiiDetection.scan_id == scan_id)
    )
    rows = result.all()

    fields_by_category: dict[str, list[str]] = defaultdict(list)
    for classification, detection in rows:
        fields_by_category[classification.category].append(detection.field_name)

    return [
        CategorySummary(category=category, field_count=len(fields), sample_fields=fields)
        for category, fields in fields_by_category.items()
    ]
