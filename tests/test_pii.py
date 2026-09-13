import io
import re

import pytest

from tests.conftest import submit_default_context

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

    await submit_default_context(client, token, scan_id)

    scan_res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scan_res.status_code == 202
    assert scan_res.json()["status"] == "scanned"
    return scan_id


# A value looks "raw" if it's a full, unmasked email/phone/PAN — i.e. it
# contains no '*' at all in a spot where masking should have redacted it.
def _looks_unmasked(masked_sample: str) -> bool:
    if "*" in masked_sample:
        return False
    # full email with a real-looking local part (more than 1 char before @)
    if re.match(r"^[\w.\-]{2,}@[\w\-]+\.[a-zA-Z]{2,}$", masked_sample):
        return True
    # a full 10+ digit run with no masking at all
    if re.fullmatch(r"\d{10,12}", masked_sample):
        return True
    return False


@pytest.mark.asyncio
async def test_clean_dataset_detects_high_medium_confidence_pii(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, CLEAN_SAMPLE_PATH)

    res = await client.get(
        f"/datasets/{scan_id}/pii",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    fields = {f["field_name"]: f for f in res.json()["fields"]}

    for expected_field in ("name", "email", "phone", "address"):
        assert expected_field in fields, f"{expected_field} not detected"
        assert fields[expected_field]["confidence"] in ("HIGH", "MEDIUM"), fields[expected_field]


@pytest.mark.asyncio
async def test_messy_dataset_flags_ambiguous_columns(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, MESSY_SAMPLE_PATH)

    res = await client.get(
        f"/datasets/{scan_id}/pii",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    fields = {f["field_name"]: f for f in res.json()["fields"]}

    assert "cust_email" in fields
    assert "contact_no" in fields


@pytest.mark.asyncio
async def test_no_raw_pii_in_pii_response_clean(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, CLEAN_SAMPLE_PATH)
    res = await client.get(
        f"/datasets/{scan_id}/pii",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    for field in res.json()["fields"]:
        assert not _looks_unmasked(field["masked_sample"]), field


@pytest.mark.asyncio
async def test_no_raw_pii_in_pii_response_messy(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, MESSY_SAMPLE_PATH)
    res = await client.get(
        f"/datasets/{scan_id}/pii",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    for field in res.json()["fields"]:
        assert not _looks_unmasked(field["masked_sample"]), field


@pytest.mark.asyncio
async def test_confidence_is_not_constant(client, auth_token):
    scan_id = await _upload_and_scan(client, auth_token, CLEAN_SAMPLE_PATH)
    res = await client.get(
        f"/datasets/{scan_id}/pii",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    confidences = {f["confidence"] for f in res.json()["fields"]}
    assert len(confidences) > 1, "confidence appears to be a fixed constant"
