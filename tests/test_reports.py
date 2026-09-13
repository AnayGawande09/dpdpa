import io
import os

import pytest
from pypdf import PdfReader

from app.pipeline.report_generator import DISCLAIMER_TEXT
from tests.conftest import submit_default_context

MESSY_SAMPLE_PATH = "data/messy_sample.csv"
CLEAN_SAMPLE_PATH = "data/clean_sample.csv"
REPORTS_DIR = "./reports"


async def _upload_scan_and_report(client, token, file_path):
    with open(file_path, "rb") as f:
        content = f.read()
    upload_res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (file_path.split("/")[-1], io.BytesIO(content), "text/csv")},
    )
    scan_id = upload_res.json()["scan_id"]
    await submit_default_context(client, token, scan_id)
    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {token}"})

    report_res = await client.post(
        f"/datasets/{scan_id}/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert report_res.status_code == 200
    return scan_id


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


@pytest.mark.asyncio
async def test_report_generates_real_pdf_on_disk(client, auth_token):
    scan_id = await _upload_scan_and_report(client, auth_token, MESSY_SAMPLE_PATH)
    file_path = os.path.join(REPORTS_DIR, f"{scan_id}.pdf")
    assert os.path.exists(file_path)
    assert os.path.getsize(file_path) > 0


@pytest.mark.asyncio
async def test_report_contains_disclaimer_verbatim(client, auth_token):
    scan_id = await _upload_scan_and_report(client, auth_token, MESSY_SAMPLE_PATH)
    file_path = os.path.join(REPORTS_DIR, f"{scan_id}.pdf")

    reader = PdfReader(file_path)
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    normalized = " ".join(full_text.split())
    assert " ".join(DISCLAIMER_TEXT.split()) in normalized


@pytest.mark.asyncio
async def test_report_contains_findings_and_score_sections(client, auth_token):
    scan_id = await _upload_scan_and_report(client, auth_token, MESSY_SAMPLE_PATH)
    file_path = os.path.join(REPORTS_DIR, f"{scan_id}.pdf")

    reader = PdfReader(file_path)
    full_text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "DPDP-R001" in full_text  # a real finding's rule_id
    assert "Risk Score" in full_text
    assert "PII Summary" in full_text


@pytest.mark.asyncio
async def test_report_contains_data_minimization_section_with_suggested_removals(client, auth_token):
    # submit_default_context uses purpose=Marketing; messy_sample.csv has
    # Government Identifier/Financial Information/Online Identifier PII,
    # none of which are necessary for Marketing.
    scan_id = await _upload_scan_and_report(client, auth_token, MESSY_SAMPLE_PATH)
    file_path = os.path.join(REPORTS_DIR, f"{scan_id}.pdf")

    reader = PdfReader(file_path)
    full_text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "Data Minimization" in full_text
    assert "Declared purpose: Marketing" in full_text
    assert "suggested for removal" in full_text
    assert "aadhaar_num" in full_text
    assert "pan_num" in full_text


@pytest.mark.asyncio
async def test_report_data_minimization_section_blank_necessary_list_for_other_purpose(client, auth_token):
    with open(MESSY_SAMPLE_PATH, "rb") as f:
        content = f.read()
    upload_res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {auth_token}"},
        files={"file": ("messy_sample.csv", io.BytesIO(content), "text/csv")},
    )
    scan_id = upload_res.json()["scan_id"]
    other_context = {
        "purpose": "Other",
        "consent_status": "Not available",
        "retention_value": 5,
        "retention_unit": "years",
        "access_scope": "Marketing,Sales",
        "encryption_enabled": False,
        "access_control_enabled": False,
        "notice_status": "Missing",
    }
    await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=other_context,
    )
    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {auth_token}"})
    await client.post(f"/datasets/{scan_id}/report", headers={"Authorization": f"Bearer {auth_token}"})

    reader = PdfReader(os.path.join(REPORTS_DIR, f"{scan_id}.pdf"))
    full_text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "Declared purpose: Other" in full_text
    assert "None defined for this purpose." in full_text


@pytest.mark.asyncio
async def test_download_report_requires_auth(client, auth_token):
    scan_id = await _upload_scan_and_report(client, auth_token, MESSY_SAMPLE_PATH)
    res = await client.get(f"/datasets/{scan_id}/report")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_download_report_returns_pdf(client, auth_token):
    scan_id = await _upload_scan_and_report(client, auth_token, MESSY_SAMPLE_PATH)
    res = await client.get(
        f"/datasets/{scan_id}/report",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 0


@pytest.mark.asyncio
async def test_report_handles_zero_findings_without_crashing(client, auth_token):
    # clean_sample.csv only has Personal Identifier / Contact Information /
    # Location PII — exactly Marketing's necessary-categories set — so this
    # context genuinely produces zero findings, including for data
    # minimization (DPDP-R008).
    good_context = {
        "purpose": "Marketing",
        "consent_status": "Available",
        "retention_value": 1,
        "retention_unit": "years",
        "access_scope": "grievance officer: privacy@example.com",
        "encryption_enabled": True,
        "access_control_enabled": True,
        "notice_status": "Available",
    }
    with open(CLEAN_SAMPLE_PATH, "rb") as f:
        content = f.read()
    upload_res = await client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {auth_token}"},
        files={"file": ("clean_sample.csv", io.BytesIO(content), "text/csv")},
    )
    scan_id = upload_res.json()["scan_id"]
    await client.post(
        f"/datasets/{scan_id}/context",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=good_context,
    )
    await client.post(f"/datasets/{scan_id}/scan", headers={"Authorization": f"Bearer {auth_token}"})

    report_res = await client.post(
        f"/datasets/{scan_id}/report",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert report_res.status_code == 200

    reader = PdfReader(os.path.join(REPORTS_DIR, f"{scan_id}.pdf"))
    full_text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "No findings for this scan." in full_text
