import pytest

from app.pipeline.gap_detector import generate_findings
from app.pipeline.rules_engine import (
    NECESSARY_CATEGORIES_BY_PURPOSE,
    load_rules,
    necessary_categories_for_purpose,
    unnecessary_categories_for_purpose,
)

ALL_SIX_CATEGORIES = {
    "Personal Identifier",
    "Contact Information",
    "Location",
    "Government Identifier",
    "Financial Information",
    "Online Identifier",
}


def test_rule_exists_and_is_data_minimization():
    rules = load_rules()
    rule = next(r for r in rules if r["rule_id"] == "DPDP-R008")
    assert rule["condition"] == "data_minimization_satisfied"
    assert rule["category"] == "Purpose Limitation"
    assert "minimiz" in rule["requirement"].lower()


@pytest.mark.parametrize(
    "purpose,expected_necessary",
    [
        ("Marketing", {"Contact Information", "Personal Identifier", "Location"}),
        ("Customer Support", {"Contact Information", "Personal Identifier"}),
        ("Analytics", {"Location", "Online Identifier"}),
        (
            "Legal/Compliance",
            {"Personal Identifier", "Contact Information", "Government Identifier", "Financial Information"},
        ),
        ("Other", set()),
    ],
)
def test_necessary_categories_defined_per_purpose(purpose, expected_necessary):
    assert necessary_categories_for_purpose(purpose) == expected_necessary


def test_other_purpose_has_blank_necessary_list():
    assert NECESSARY_CATEGORIES_BY_PURPOSE["Other"] == set()


def test_unnecessary_categories_computed_correctly_for_marketing():
    unnecessary = unnecessary_categories_for_purpose(ALL_SIX_CATEGORIES, "Marketing")
    assert unnecessary == {"Government Identifier", "Financial Information", "Online Identifier"}


def test_no_unnecessary_categories_when_dataset_matches_purpose_exactly():
    marketing_fields = {"Contact Information", "Personal Identifier", "Location"}
    assert unnecessary_categories_for_purpose(marketing_fields, "Marketing") == set()


def test_other_purpose_flags_everything_detected_as_unnecessary():
    assert unnecessary_categories_for_purpose(ALL_SIX_CATEGORIES, "Other") == ALL_SIX_CATEGORIES


def test_unknown_purpose_string_treated_as_no_necessary_fields():
    # defensive: an unrecognized purpose value behaves like "Other"
    assert unnecessary_categories_for_purpose({"Location"}, "Something Unmapped") == {"Location"}


def test_gap_detector_cites_only_unnecessary_fields_for_data_minimization():
    rules_by_id = {r["rule_id"]: r for r in load_rules()}
    category_to_fields = {
        "Personal Identifier": ["full_nm"],
        "Contact Information": ["cust_email", "contact_no"],
        "Government Identifier": ["aadhaar_num"],
        "Financial Information": ["pan_num"],
        "Location": ["loc"],
        "Online Identifier": ["ip_addr"],
    }
    fail_evaluations = [
        {
            "rule_id": "DPDP-R008",
            "category": "Purpose Limitation",
            "severity": "MEDIUM",
            "evidence_field": "data_minimization",
        }
    ]
    findings = generate_findings(fail_evaluations, category_to_fields, "Marketing", rules_by_id)
    assert len(findings) == 1
    finding = findings[0]
    assert set(finding.affected_fields) == {"aadhaar_num", "pan_num", "ip_addr"}
    assert "full_nm" not in finding.affected_fields  # necessary for Marketing, not flagged
    assert "Data Minimization" in finding.missing_control
