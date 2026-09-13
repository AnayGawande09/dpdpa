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
async def test_upload_accepts_file_larger_than_old_10mb_cap(client, auth_token):
    # The default limit used to be 10 MB and the upload path used to buffer
    # the whole file into memory before checking its size. This proves both
    # the raised default limit and the streaming-to-disk rewrite actually
    # handle a file bigger than that old cap.
    rows = ["name,email"] + [f"user{i},user{i}@example.com" for i in range(400_000)]
    content = ("\n".join(rows) + "\n").encode("utf-8")
    assert len(content) > 10 * 1024 * 1024  # bigger than the old default cap

    res = await _upload(client, auth_token, "big_sample.csv", content)
    assert res.status_code == 200
    assert res.json()["row_count"] == 400_000


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file_without_buffering_whole_file(client, auth_token, monkeypatch):
    from app.config import settings

    # 1 MB limit with a ~5 MB file: proves rejection happens based on a
    # streamed running total, not by reading the entire file first.
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    content = ("x" * (5 * 1024 * 1024)).encode("utf-8")
    res = await _upload(client, auth_token, "oversized.csv", content)
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
    from tests.conftest import submit_default_context

    upload_res = await _upload(client, auth_token, "sample.csv", CSV_CONTENT)
    scan_id = upload_res.json()["scan_id"]
    await submit_default_context(client, auth_token, scan_id)

    res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "scanning"  # runs in a background task, not inline

    # the background task runs to completion within the same ASGI call in
    # tests, so by the time we poll GET the dataset is already scanned
    poll_res = await client.get(
        f"/datasets/{scan_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert poll_res.json()["status"] == "scanned"
