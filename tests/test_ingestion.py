import io

import pandas as pd
import pytest


async def _upload(client, token, filename, content: bytes, content_type="text/csv"):
    return await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


CSV_CONTENT = b"name,email\nRavi,ravi@example.com\nAnita,anita@example.com\n"


@pytest.mark.asyncio
async def test_upload_csv(client, auth_token):
    res = await _upload(client, auth_token, "sample.csv", CSV_CONTENT)
    assert res.status_code == 200
    data = res.json()
    assert data["row_count"] == 2
    assert data["column_names"] == ["name", "email"]
    assert "scan_id" in data


@pytest.mark.asyncio
async def test_upload_json(client, auth_token):
    content = b'[{"name": "Ravi", "email": "ravi@example.com"}]'
    res = await _upload(client, auth_token, "sample.json", content, "application/json")
    assert res.status_code == 200
    data = res.json()
    assert data["row_count"] == 1
    assert "name" in data["column_names"]


@pytest.mark.asyncio
async def test_upload_txt(client, auth_token):
    res = await _upload(client, auth_token, "sample.txt", CSV_CONTENT, "text/plain")
    assert res.status_code == 200
    data = res.json()
    assert data["row_count"] == 2


@pytest.mark.asyncio
async def test_upload_xlsx(client, auth_token):
    df = pd.DataFrame({"name": ["Ravi", "Anita"], "email": ["ravi@example.com", "anita@example.com"]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    res = await _upload(
        client,
        auth_token,
        "sample.xlsx",
        buf.read(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert res.status_code == 200
    data = res.json()
    assert data["row_count"] == 2
    assert data["column_names"] == ["name", "email"]


@pytest.mark.asyncio
async def test_upload_rejects_invalid_extension(client, auth_token):
    res = await _upload(client, auth_token, "sample.exe", b"not a real file", "application/octet-stream")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, auth_token, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)
    res = await _upload(client, auth_token, "sample.csv", CSV_CONTENT)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_get_dataset_404_on_unknown_scan_id(client, auth_token):
    res = await client.get(
        "/datasets/does-not-exist",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_dataset_returns_metadata(client, auth_token):
    upload_res = await _upload(client, auth_token, "sample.csv", CSV_CONTENT)
    scan_id = upload_res.json()["scan_id"]

    res = await client.get(
        f"/datasets/{scan_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["scan_id"] == scan_id
    assert data["status"] == "uploaded"


@pytest.mark.asyncio
async def test_scan_requires_auth(client, auth_token):
    upload_res = await _upload(client, auth_token, "sample.csv", CSV_CONTENT)
    scan_id = upload_res.json()["scan_id"]

    res = await client.post(f"/datasets/{scan_id}/scan")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_scan_runs_detection_and_completes(client, auth_token):
    upload_res = await _upload(client, auth_token, "sample.csv", CSV_CONTENT)
    scan_id = upload_res.json()["scan_id"]

    res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "scanned"
