import json
import os
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.dataset import Dataset, DatasetStatus
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.dataset import DatasetResponse, ScanAcceptedResponse, UploadResponse

router = APIRouter(prefix="/datasets", tags=["ingestion"])

ALLOWED_EXTENSIONS = {".csv", ".json", ".txt", ".xlsx"}


def _parse_file(file_path: str, extension: str) -> tuple[int, list[str]]:
    if extension in (".csv", ".txt"):
        df = pd.read_csv(file_path)
    elif extension == ".xlsx":
        df = pd.read_excel(file_path)
    elif extension == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data if isinstance(data, list) else [data])
    else:
        raise ValueError(f"Unsupported extension: {extension}")
    return len(df), [str(c) for c in df.columns]


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{extension}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    contents = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds max upload size of {settings.MAX_UPLOAD_MB} MB",
        )

    scan_id = str(uuid.uuid4())
    scan_dir = os.path.join(settings.UPLOAD_DIR, scan_id)
    os.makedirs(scan_dir, exist_ok=True)
    file_path = os.path.join(scan_dir, filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    try:
        row_count, column_names = _parse_file(file_path, extension)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse file: {exc}",
        )

    dataset = Dataset(
        id=scan_id,
        filename=filename,
        uploaded_by=current_user.id,
        row_count=row_count,
        column_names=column_names,
        file_path=file_path,
        status=DatasetStatus.uploaded,
    )
    db.add(dataset)
    await db.commit()

    return UploadResponse(
        scan_id=scan_id,
        filename=filename,
        row_count=row_count,
        column_names=column_names,
    )


async def _get_dataset_or_404(scan_id: str, db: AsyncSession) -> Dataset:
    result = await db.execute(select(Dataset).where(Dataset.id == scan_id))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


@router.get("/{scan_id}", response_model=DatasetResponse)
async def get_dataset(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_dataset_or_404(scan_id, db)
    return DatasetResponse(
        scan_id=dataset.id,
        filename=dataset.filename,
        row_count=dataset.row_count,
        column_names=dataset.column_names,
        status=dataset.status,
        uploaded_at=dataset.uploaded_at,
    )


@router.post("/{scan_id}/scan", response_model=ScanAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_scan(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_dataset_or_404(scan_id, db)
    # Stub for Phase 1 — later phases implement the real pipeline behind this endpoint.
    dataset.status = DatasetStatus.scanning
    await db.commit()
    return ScanAcceptedResponse(scan_id=dataset.id, status=dataset.status)
