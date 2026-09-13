from app.pipeline.gap_detector import generate_findings
from app.pipeline.rules_engine import load_rules

RULES_BY_ID = {rule["rule_id"]: rule for rule in load_rules()}

CATEGORY_TO_FIELDS = {
    "Personal Identifier": ["full_nm"],
    "Contact Information": ["cust_email", "contact_no"],
    "Government Identifier": ["aadhaar_num"],
    "Financial Information": ["pan_num"],
}


def test_every_finding_has_rule_id_and_evidence():
    fail_evaluations = [
        {"rule_id": "DPDP-R001", "category": "Consent", "severity": "HIGH", "evidence_field": "consent_status"},
        {"rule_id": "DPDP-R004", "category": "Access Control", "severity": "CRITICAL", "evidence_field": "access_control_enabled"},
    ]
    findings = generate_findings(fail_evaluations, CATEGORY_TO_FIELDS, "Marketing", RULES_BY_ID)
    assert len(findings) == 2
    for finding in findings:
        assert finding.rule_id
        assert finding.evidence
        assert finding.explanation


def test_sensitive_only_rule_restricts_affected_fields():
    fail_evaluations = [
        {"rule_id": "DPDP-R004", "category": "Access Control", "severity": "CRITICAL", "evidence_field": "access_control_enabled"},
    ]
    findings = generate_findings(fail_evaluations, CATEGORY_TO_FIELDS, "Marketing", RULES_BY_ID)
    assert set(findings[0].affected_fields) == {"aadhaar_num", "pan_num"}


def test_dataset_wide_rule_includes_all_fields():
    fail_evaluations = [
        {"rule_id": "DPDP-R001", "category": "Consent", "severity": "HIGH", "evidence_field": "consent_status"},
    ]
    findings = generate_findings(fail_evaluations, CATEGORY_TO_FIELDS, "Marketing", RULES_BY_ID)
    affected = set(findings[0].affected_fields)
    assert affected == {"full_nm", "cust_email", "contact_no", "aadhaar_num", "pan_num"}


def test_explanation_references_real_fields_purpose_and_rule_id():
    fail_evaluations = [
        {"rule_id": "DPDP-R001", "category": "Consent", "severity": "HIGH", "evidence_field": "consent_status"},
    ]
    findings = generate_findings(fail_evaluations, CATEGORY_TO_FIELDS, "Marketing", RULES_BY_ID)
    explanation = findings[0].explanation
    assert "Marketing" in explanation
    assert "DPDP-R001" in explanation
    assert "Recorded Consent" in explanation
    assert "cust_email" in explanation


def test_no_findings_for_empty_fail_list():
    assert generate_findings([], CATEGORY_TO_FIELDS, "Marketing", RULES_BY_ID) == []
