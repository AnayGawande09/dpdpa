import io

import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.pii_classification import PiiClassification
from app.models.pii_detection import PiiDetection

CLEAN_SAMPLE_PATH = "data/clean_sample.csv"
MESSY_SAMPLE_PATH = "data/messy_sample.csv"


async def _upload_and_scan(client, token, file_path):
    with open(file_path, "rb") as f:
        content = f.read()
    upload_res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (file_path.split("/")[-1], io.BytesIO(content), "text/csv")},
    )
    assert upload_res.status_code == 200
    scan_id = upload_res.json()["scan_id"]

    scan_res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scan_res.status_code == 202
    return scan_id


@pytest.mark.asyncio
async def test_every_detection_gets_exactly_one_classification_clean(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, CLEAN_SAMPLE_PATH)

    async with AsyncSessionLocal() as db:
        detection_result = await db.execute(select(PiiDetection).where(PiiDetection.scan_id == scan_id))
        detections = detection_result.scalars().all()
        detection_ids = [d.id for d in detections]

        classification_result = await db.execute(
            select(PiiClassification).where(PiiClassification.detection_id.in_(detection_ids))
        )
        classifications = classification_result.scalars().all()

    assert len(detections) > 0
    assert len(classifications) == len(detections)


@pytest.mark.asyncio
async def test_every_detection_gets_exactly_one_classification_messy(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, MESSY_SAMPLE_PATH)

    async with AsyncSessionLocal() as db:
        detection_result = await db.execute(select(PiiDetection).where(PiiDetection.scan_id == scan_id))
        detections = detection_result.scalars().all()
        detection_ids = [d.id for d in detections]

        classification_result = await db.execute(
            select(PiiClassification).where(PiiClassification.detection_id.in_(detection_ids))
        )
        classifications = classification_result.scalars().all()

    assert len(detections) > 0
    assert len(classifications) == len(detections)


@pytest.mark.asyncio
async def test_pii_summary_returns_accurate_rollup_for_messy_dataset(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, MESSY_SAMPLE_PATH)

    res = await client.get(
        f"/datasets/{scan_id}/pii/summary",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    summary = res.json()
    categories = {row["category"] for row in summary}

    # messy_sample.csv exercises all six taxonomy categories in one scan
    assert categories == {
        "Personal Identifier",
        "Contact Information",
        "Location",
        "Government Identifier",
        "Financial Information",
        "Online Identifier",
    }
    for row in summary:
        assert row["field_count"] == len(row["sample_fields"])


@pytest.mark.asyncio
async def test_pii_summary_fallback_path_for_ambiguous_dob_column(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, CLEAN_SAMPLE_PATH)

    res = await client.get(
        f"/datasets/{scan_id}/pii/summary",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    summary = res.json()
    personal_identifier_row = next(row for row in summary if row["category"] == "Personal Identifier")
    assert "dob" in personal_identifier_row["sample_fields"]
