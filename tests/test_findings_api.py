import io

import pytest

from tests.conftest import submit_default_context

MESSY_SAMPLE_PATH = "data/messy_sample.csv"
CLEAN_SAMPLE_PATH = "data/clean_sample.csv"

# clean_sample.csv only has Personal Identifier / Contact Information /
# Location PII — exactly Marketing's necessary-categories set — so this
# context can genuinely satisfy every rule, including data minimization.
GOOD_CONTEXT = {
    "purpose": "Marketing",
    "consent_status": "Available",
    "retention_value": 1,
    "retention_unit": "years",
    "access_scope": "grievance officer: privacy@example.com",
    "encryption_enabled": True,
    "access_control_enabled": True,
    "notice_status": "Available",
}


async def _upload(client, token, file_path):
    with open(file_path, "rb") as f:
        content = f.read()
    res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (file_path.split("/")[-1], io.BytesIO(content), "text/csv")},
    )
    assert res.status_code == 200
    return res.json()["scan_id"]


@pytest.mark.asyncio
async def test_findings_generated_for_bad_context_scan(client, auth_token):
    scan_id = await _upload(client, auth_token, MESSY_SAMPLE_PATH)
    await submit_default_context(client, auth_token, scan_id)

    scan_res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert scan_res.status_code == 202

    findings_res = await client.get(
        f"/datasets/{scan_id}/findings",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert findings_res.status_code == 200
    findings = findings_res.json()
    assert len(findings) > 0
    for finding in findings:
        assert finding["rule_id"]
        assert finding["evidence"]
        assert finding["explanation"]


@pytest.mark.asyncio
async def test_risk_score_for_bad_context_lands_high_or_critical(client, auth_token):
    scan_id = await _upload(client, auth_token, MESSY_SAMPLE_PATH)
    await submit_default_context(client, auth_token, scan_id)
    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {auth_token}"})

    risk_res = await client.get(
        f"/datasets/{scan_id}/risk",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert risk_res.status_code == 200
    risk = risk_res.json()
    assert risk["band"] in ("High", "Critical")
    assert sum(item["points_added"] for item in risk["breakdown"]) == risk["score"]


@pytest.mark.asyncio
async def test_risk_score_for_good_context_lands_low(client, auth_token):
    scan_id = await _upload(client, auth_token, CLEAN_SAMPLE_PATH)
    await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=GOOD_CONTEXT,
    )
    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {auth_token}"})

    risk_res = await client.get(
        f"/datasets/{scan_id}/risk",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert risk_res.json()["band"] == "Low"


@pytest.mark.asyncio
async def test_rescanning_does_not_duplicate_findings_or_risk_scores(client, auth_token):
    scan_id = await _upload(client, auth_token, MESSY_SAMPLE_PATH)
    await submit_default_context(client, auth_token, scan_id)

    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {auth_token}"})
    first_findings = (
        await client.get(f"/datasets/{scan_id}/findings", headers={"Authorization": f"Bearer {auth_token}"})
    ).json()

    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {auth_token}"})
    second_findings = (
        await client.get(f"/datasets/{scan_id}/findings", headers={"Authorization": f"Bearer {auth_token}"})
    ).json()

    assert len(first_findings) == len(second_findings)

    risk_res = await client.get(
        f"/datasets/{scan_id}/risk",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert risk_res.status_code == 200  # exactly one risk_scores row exists (unique scan_id)
