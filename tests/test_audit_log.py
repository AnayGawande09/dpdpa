import io
import os

import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.audit_log import AuditLog
from tests.conftest import submit_default_context

MESSY_SAMPLE_PATH = "data/messy_sample.csv"
REPORTS_DIR = "./reports"


@pytest.fixture(autouse=True)
def cleanup_reports():
    yield
    if os.path.isdir(REPORTS_DIR):
        for f in os.listdir(REPORTS_DIR):
            if f.endswith(".pdf"):
                try:
                    os.remove(os.path.join(REPORTS_DIR, f))
                except OSError:
                    pass


async def _full_flow(client, token):
    with open(MESSY_SAMPLE_PATH, "rb") as f:
        content = f.read()
    upload_res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("messy_sample.csv", io.BytesIO(content), "text/csv")},
    )
    scan_id = upload_res.json()["scan_id"]
    await submit_default_context(client, token, scan_id)
    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {token}"})
    await client.post(f"/datasets/{scan_id}/report", headers={"Authorization": f"Bearer {token}"})
    return scan_id


@pytest.mark.asyncio
async def test_every_action_produces_exactly_one_audit_row(client, auth_token):
    scan_id = await _full_flow(client, auth_token)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AuditLog).where(AuditLog.scan_id == scan_id))
        rows = result.scalars().all()

    actions = [r.action.value for r in rows]
    assert actions.count("upload") == 1
    assert actions.count("context_submitted") == 1
    assert actions.count("scan_run") == 1
    assert actions.count("report_exported") == 1

    async with AsyncSessionLocal() as db:
        login_result = await db.execute(select(AuditLog).where(AuditLog.action == "login"))
        login_rows = login_result.scalars().all()
    assert len(login_rows) >= 1


@pytest.mark.asyncio
async def test_audit_log_endpoint_filters_by_scan_id(client, auth_token):
    scan_id = await _full_flow(client, auth_token)

    res = await client.get(
        f"/audit-log?scan_id={scan_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4  # upload, context_submitted, scan_run, report_exported
    assert all(item["scan_id"] == scan_id for item in data["items"])


@pytest.mark.asyncio
async def test_audit_log_endpoint_filters_by_action(client, auth_token):
    await _full_flow(client, auth_token)

    res = await client.get(
        "/audit-log?action=report_exported",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    data = res.json()
    assert data["total"] >= 1
    assert all(item["action"] == "report_exported" for item in data["items"])


@pytest.mark.asyncio
async def test_audit_log_endpoint_pagination(client, auth_token):
    await _full_flow(client, auth_token)
    await _full_flow(client, auth_token)

    res = await client.get(
        "/audit-log?page=1&page_size=2",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    data = res.json()
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] >= 8


@pytest.mark.asyncio
async def test_audit_log_requires_auth(client):
    res = await client.get("/audit-log")
    assert res.status_code == 401
