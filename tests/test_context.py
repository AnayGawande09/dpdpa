import io

import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.processing_context import ProcessingContext

CSV_CONTENT = b"name,email\nRavi,ravi@example.com\n"

GOOD_CONTEXT = {
    "purpose": "Marketing",
    "consent_status": "Not available",
    "retention_value": 5,
    "retention_unit": "years",
    "access_scope": "Marketing,Sales",
    "encryption_enabled": False,
    "access_control_enabled": False,
    "notice_status": "Missing",
}


async def _upload(client, token):
    res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("sample.csv", io.BytesIO(CSV_CONTENT), "text/csv")},
    )
    assert res.status_code == 200
    return res.json()["scan_id"]


@pytest.mark.asyncio
async def test_scan_returns_400_without_context(client, auth_token):
    scan_id = await _upload(client, auth_token)
    res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_scan_succeeds_once_context_exists(client, auth_token):
    scan_id = await _upload(client, auth_token)
    context_res = await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=GOOD_CONTEXT,
    )
    assert context_res.status_code == 200

    scan_res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert scan_res.status_code == 202


@pytest.mark.asyncio
async def test_get_context_returns_defaults_when_not_submitted(client, auth_token):
    scan_id = await _upload(client, auth_token)
    res = await client.get(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["submitted"] is False
    assert data["purpose"] == "Marketing"
    assert data["consent_status"] == "Unknown"
    assert data["retention_value"] == 5
    assert data["retention_unit"] == "years"
    assert data["encryption_enabled"] is False
    assert data["access_control_enabled"] is False


@pytest.mark.asyncio
async def test_get_context_returns_submitted_values(client, auth_token):
    scan_id = await _upload(client, auth_token)
    await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=GOOD_CONTEXT,
    )
    res = await client.get(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    data = res.json()
    assert data["submitted"] is True
    assert data["access_scope"] == "Marketing,Sales"


@pytest.mark.asyncio
async def test_submitting_context_twice_updates_not_duplicates(client, auth_token):
    scan_id = await _upload(client, auth_token)
    await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=GOOD_CONTEXT,
    )
    updated = dict(GOOD_CONTEXT, purpose="Analytics", retention_value=2, retention_unit="years")
    res2 = await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=updated,
    )
    assert res2.status_code == 200
    assert res2.json()["purpose"] == "Analytics"

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ProcessingContext).where(ProcessingContext.scan_id == scan_id))
        rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].purpose.value == "Analytics"
