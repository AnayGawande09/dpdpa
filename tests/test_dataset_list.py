import io

import pytest

CSV_CONTENT = b"name,email\nRavi,ravi@example.com\n"


async def _upload(client, token, filename):
    res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, io.BytesIO(CSV_CONTENT), "text/csv")},
    )
    assert res.status_code == 200
    return res.json()["scan_id"]


@pytest.mark.asyncio
async def test_list_datasets_requires_auth(client):
    res = await client.get("/datasets")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_datasets_returns_uploaded_scans(client, auth_token):
    await _upload(client, auth_token, "a.csv")
    await _upload(client, auth_token, "b.csv")

    res = await client.get("/datasets", headers={"Authorization": f"Bearer {auth_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2
    filenames = {item["filename"] for item in data["items"]}
    assert "a.csv" in filenames or "b.csv" in filenames  # page_size may limit results


@pytest.mark.asyncio
async def test_list_datasets_pagination(client, auth_token):
    for i in range(3):
        await _upload(client, auth_token, f"file{i}.csv")

    res = await client.get("/datasets?page=1&page_size=2", headers={"Authorization": f"Bearer {auth_token}"})
    data = res.json()
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] >= 3

    res2 = await client.get("/datasets?page=2&page_size=2", headers={"Authorization": f"Bearer {auth_token}"})
    data2 = res2.json()
    assert data2["page"] == 2
    # no overlap between page 1 and page 2 items
    page1_ids = {item["scan_id"] for item in data["items"]}
    page2_ids = {item["scan_id"] for item in data2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_list_datasets_orders_newest_first(client, auth_token):
    first_id = await _upload(client, auth_token, "first.csv")
    second_id = await _upload(client, auth_token, "second.csv")

    res = await client.get("/datasets?page=1&page_size=10", headers={"Authorization": f"Bearer {auth_token}"})
    ids_in_order = [item["scan_id"] for item in res.json()["items"]]
    assert ids_in_order.index(second_id) < ids_in_order.index(first_id)
