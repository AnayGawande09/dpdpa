import io

import pytest

from tests.conftest import submit_default_context

MESSY_SAMPLE_PATH = "data/messy_sample.csv"
CLEAN_SAMPLE_PATH = "data/clean_sample.csv"

# clean_sample.csv only contains Personal Identifier / Contact Information /
# Location PII — exactly Marketing's necessary-categories set — so a
# Marketing-purpose context on this dataset can genuinely pass every rule,
# including data minimization (DPDP-R008).
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
async def test_rules_run_as_part_of_scan_with_default_bad_context(client, auth_token):
    scan_id = await _upload(client, auth_token, MESSY_SAMPLE_PATH)
    await submit_default_context(client, auth_token, scan_id)  # weak defaults: no encryption/access control

    scan_res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert scan_res.status_code == 202

    rules_res = await client.get(
        f"/datasets/{scan_id}/rules",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert rules_res.status_code == 200
    evaluations = rules_res.json()
    assert len(evaluations) >= 6

    outcomes = {e["rule_id"]: e["outcome"] for e in evaluations}
    # messy_sample.csv has Government Identifier + Financial Information PII,
    # and submit_default_context leaves encryption/access control disabled.
    assert outcomes["DPDP-R004"] == "FAIL"  # access control
    assert outcomes["DPDP-R005"] == "FAIL"  # encryption


@pytest.mark.asyncio
async def test_rules_all_pass_with_good_context(client, auth_token):
    scan_id = await _upload(client, auth_token, CLEAN_SAMPLE_PATH)
    ctx_res = await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=GOOD_CONTEXT,
    )
    assert ctx_res.status_code == 200

    scan_res = await client.post(
        f"/datasets/{scan_id}/scan",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert scan_res.status_code == 202

    rules_res = await client.get(
        f"/datasets/{scan_id}/rules",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    evaluations = rules_res.json()
    outcomes = {e["rule_id"]: e["outcome"] for e in evaluations}
    assert all(outcome == "PASS" for outcome in outcomes.values()), outcomes
