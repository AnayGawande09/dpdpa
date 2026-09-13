import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.db import get_db
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User
from app.pipeline.report_generator import generate_report_pdf
from app.routers.auth import get_current_user
from app.routers.ingestion import _get_dataset_or_404
from app.schemas.reports import AuditLogEntry, AuditLogListResponse, ReportResponse

router = APIRouter(tags=["reports"])

REPORTS_DIR = "./reports"


@router.post("/datasets/{scan_id}/report", response_model=ReportResponse)
async def create_report(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    file_path = await generate_report_pdf(scan_id, db, reports_dir=REPORTS_DIR)

    await record_audit(
        db, user_id=current_user.id, action=AuditAction.report_exported, scan_id=scan_id
    )
    await db.commit()

    return ReportResponse(
        scan_id=scan_id,
        file_path=file_path,
        download_url=f"/datasets/{scan_id}/report",
    )


@router.get("/datasets/{scan_id}/report")
async def download_report(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    file_path = os.path.join(REPORTS_DIR, f"{scan_id}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not generated yet. POST /datasets/{scan_id}/report first.",
        )
    return FileResponse(file_path, media_type="application/pdf", filename=f"{scan_id}.pdf")


@router.get("/audit-log", response_model=AuditLogListResponse)
async def list_audit_log(
    page: int = 1,
    page_size: int = 20,
    scan_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))

    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)
    if scan_id:
        query = query.where(AuditLog.scan_id == scan_id)
        count_query = count_query.where(AuditLog.scan_id == scan_id)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(AuditLog.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    rows = result.scalars().all()

    return AuditLogListResponse(
        items=[
            AuditLogEntry(
                id=r.id,
                user_id=r.user_id,
                scan_id=r.scan_id,
                action=r.action.value,
                details=r.details,
                occurred_at=r.occurred_at,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
