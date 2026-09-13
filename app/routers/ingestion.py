import json
import os
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.config import settings
from app.db import get_db
from app.models.audit_log import AuditAction
from app.models.dataset import Dataset, DatasetStatus
from app.models.pii_classification import PiiClassification
from app.models.pii_detection import Confidence, DetectorType, PiiDetection
from app.models.finding import Finding
from app.models.processing_context import ProcessingContext
from app.models.risk_score import RiskScore
from app.models.rule_evaluation import RuleEvaluationRow
from app.models.user import User
from app.pipeline.classification import classify_detection
from app.pipeline.detection import detect_pii
from app.pipeline.gap_detector import generate_findings
from app.pipeline.risk_engine import compute_risk
from app.pipeline.rules_engine import evaluate_rules, load_rules
from app.routers.auth import get_current_user
from app.schemas.context import DEFAULT_CONTEXT, ProcessingContextIn, ProcessingContextOut
from app.schemas.dataset import DatasetListResponse, DatasetResponse, ScanAcceptedResponse, UploadResponse

router = APIRouter(prefix="/datasets", tags=["ingestion"])

ALLOWED_EXTENSIONS = {".csv", ".json", ".txt", ".xlsx"}


def load_dataframe(file_path: str, extension: str) -> pd.DataFrame:
    if extension in (".csv", ".txt"):
        return pd.read_csv(file_path)
    if extension == ".xlsx":
        return pd.read_excel(file_path)
    if extension == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return pd.DataFrame(data if isinstance(data, list) else [data])
    raise ValueError(f"Unsupported extension: {extension}")


def _parse_file(file_path: str, extension: str) -> tuple[int, list[str]]:
    df = load_dataframe(file_path, extension)
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
    await record_audit(
        db, user_id=current_user.id, action=AuditAction.upload, scan_id=scan_id, details={"filename": filename}
    )
    await db.commit()

    return UploadResponse(
        scan_id=scan_id,
        filename=filename,
        row_count=row_count,
        column_names=column_names,
    )


@router.get("", response_model=DatasetListResponse)
async def list_datasets(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))

    total = (await db.execute(select(func.count()).select_from(Dataset))).scalar_one()
    result = await db.execute(
        select(Dataset).order_by(Dataset.uploaded_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    datasets = result.scalars().all()

    return DatasetListResponse(
        items=[
            DatasetResponse(
                scan_id=d.id,
                filename=d.filename,
                row_count=d.row_count,
                column_names=d.column_names,
                status=d.status,
                uploaded_at=d.uploaded_at,
            )
            for d in datasets
        ],
        total=total,
        page=page,
        page_size=page_size,
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


async def _get_context(scan_id: str, db: AsyncSession) -> ProcessingContext | None:
    result = await db.execute(select(ProcessingContext).where(ProcessingContext.scan_id == scan_id))
    return result.scalar_one_or_none()


@router.post("/{scan_id}/context", response_model=ProcessingContextOut)
async def submit_context(
    scan_id: str,
    payload: ProcessingContextIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    context = await _get_context(scan_id, db)

    if context is None:
        context = ProcessingContext(scan_id=scan_id, submitted_by=current_user.id)
        db.add(context)

    context.purpose = payload.purpose
    context.consent_status = payload.consent_status
    context.retention_value = payload.retention_value
    context.retention_unit = payload.retention_unit
    context.access_scope = payload.access_scope
    context.encryption_enabled = payload.encryption_enabled
    context.access_control_enabled = payload.access_control_enabled
    context.notice_status = payload.notice_status
    context.submitted_by = current_user.id

    await record_audit(db, user_id=current_user.id, action=AuditAction.context_submitted, scan_id=scan_id)
    await db.commit()
    await db.refresh(context)

    return ProcessingContextOut(
        scan_id=context.scan_id,
        purpose=context.purpose,
        consent_status=context.consent_status,
        retention_value=context.retention_value,
        retention_unit=context.retention_unit,
        access_scope=context.access_scope,
        encryption_enabled=context.encryption_enabled,
        access_control_enabled=context.access_control_enabled,
        notice_status=context.notice_status,
        submitted=True,
        submitted_at=context.submitted_at,
    )


@router.get("/{scan_id}/context", response_model=ProcessingContextOut)
async def get_context(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_dataset_or_404(scan_id, db)
    context = await _get_context(scan_id, db)

    if context is None:
        return ProcessingContextOut(scan_id=scan_id, submitted=False, submitted_at=None, **DEFAULT_CONTEXT)

    return ProcessingContextOut(
        scan_id=context.scan_id,
        purpose=context.purpose,
        consent_status=context.consent_status,
        retention_value=context.retention_value,
        retention_unit=context.retention_unit,
        access_scope=context.access_scope,
        encryption_enabled=context.encryption_enabled,
        access_control_enabled=context.access_control_enabled,
        notice_status=context.notice_status,
        submitted=True,
        submitted_at=context.submitted_at,
    )


@router.post("/{scan_id}/scan", response_model=ScanAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_scan(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_dataset_or_404(scan_id, db)

    context = await _get_context(scan_id, db)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Processing context must be submitted before scanning. "
            f"POST /datasets/{scan_id}/context first.",
        )

    dataset.status = DatasetStatus.scanning
    await db.commit()

    # Clean up any prior scan's rows for this scan_id so re-running /scan
    # doesn't duplicate detections/classifications/rules/findings.
    old_detection_ids = (
        await db.execute(select(PiiDetection.id).where(PiiDetection.scan_id == scan_id))
    ).scalars().all()
    if old_detection_ids:
        await db.execute(delete(PiiClassification).where(PiiClassification.detection_id.in_(old_detection_ids)))
    await db.execute(delete(PiiDetection).where(PiiDetection.scan_id == scan_id))
    await db.execute(delete(RuleEvaluationRow).where(RuleEvaluationRow.scan_id == scan_id))
    await db.execute(delete(Finding).where(Finding.scan_id == scan_id))
    await db.commit()

    extension = os.path.splitext(dataset.filename)[1].lower()
    df = load_dataframe(dataset.file_path, extension)
    detections = detect_pii(df)

    pii_categories: set[str] = set()
    category_to_fields: dict[str, list[str]] = {}
    detection_confidences: list[str] = []
    for detection in detections:
        detection_row = PiiDetection(
            scan_id=scan_id,
            field_name=detection.field_name,
            masked_sample=detection.masked_sample,
            detector_type=DetectorType(detection.detector_type),
            confidence=Confidence(detection.confidence),
        )
        db.add(detection_row)
        await db.flush()  # populate detection_row.id for the classification FK
        detection_confidences.append(detection.confidence)

        classification = classify_detection(
            detector_type=detection.detector_type,
            field_name=detection.field_name,
            detection_confidence=detection.confidence,
        )
        pii_categories.add(classification.category)
        category_to_fields.setdefault(classification.category, []).append(detection.field_name)
        db.add(
            PiiClassification(
                detection_id=detection_row.id,
                category=classification.category,
                subtype=classification.subtype,
                confidence=classification.confidence,
                source=classification.source,
            )
        )

    context_dict = {
        "purpose": context.purpose.value,
        "consent_status": context.consent_status.value,
        "retention_value": context.retention_value,
        "retention_unit": context.retention_unit.value,
        "access_scope": context.access_scope,
        "encryption_enabled": context.encryption_enabled,
        "access_control_enabled": context.access_control_enabled,
        "notice_status": context.notice_status.value,
    }
    rule_evaluations = evaluate_rules(pii_categories, context_dict)
    for evaluation in rule_evaluations:
        db.add(
            RuleEvaluationRow(
                scan_id=scan_id,
                rule_id=evaluation.rule_id,
                category=evaluation.category,
                severity=evaluation.severity,
                outcome=evaluation.outcome,
                evidence_field=evaluation.evidence_field,
            )
        )

    fail_evaluations = [
        {
            "rule_id": e.rule_id,
            "category": e.category,
            "severity": e.severity,
            "outcome": e.outcome,
            "evidence_field": e.evidence_field,
        }
        for e in rule_evaluations
        if e.outcome == "FAIL"
    ]
    rules_by_id = {rule["rule_id"]: rule for rule in load_rules()}
    findings = generate_findings(fail_evaluations, category_to_fields, context_dict["purpose"], rules_by_id)
    for finding in findings:
        db.add(
            Finding(
                scan_id=scan_id,
                category=finding.category,
                affected_fields=finding.affected_fields,
                purpose=finding.purpose,
                missing_control=finding.missing_control,
                rule_id=finding.rule_id,
                evidence=finding.evidence,
                severity=finding.severity,
                explanation=finding.explanation,
            )
        )

    all_evaluations_for_risk = [
        {"rule_id": e.rule_id, "severity": e.severity, "outcome": e.outcome} for e in rule_evaluations
    ]
    risk_result = compute_risk(
        pii_categories, detection_confidences, all_evaluations_for_risk, context_dict["access_scope"]
    )
    existing_risk_score = await db.execute(select(RiskScore).where(RiskScore.scan_id == scan_id))
    risk_score_row = existing_risk_score.scalar_one_or_none()
    breakdown_json = [
        {"factor": item.factor, "points_added": item.points_added, "reason": item.reason}
        for item in risk_result.breakdown
    ]
    if risk_score_row is None:
        db.add(
            RiskScore(
                scan_id=scan_id,
                score=risk_result.score,
                band=risk_result.band,
                breakdown=breakdown_json,
            )
        )
    else:
        risk_score_row.score = risk_result.score
        risk_score_row.band = risk_result.band
        risk_score_row.breakdown = breakdown_json

    dataset.status = DatasetStatus.scanned
    await record_audit(
        db,
        user_id=current_user.id,
        action=AuditAction.scan_run,
        scan_id=scan_id,
        details={"risk_score": risk_result.score, "risk_band": risk_result.band},
    )
    await db.commit()
    return ScanAcceptedResponse(scan_id=dataset.id, status=dataset.status)
