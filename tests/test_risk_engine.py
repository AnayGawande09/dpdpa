import pytest

from app.pipeline.risk_engine import band_for_score, compute_risk

SENSITIVE_CATEGORIES = {
    "Personal Identifier",
    "Contact Information",
    "Location",
    "Government Identifier",
    "Financial Information",
    "Online Identifier",
}

BAD_EVALUATIONS = [
    {"rule_id": "DPDP-R001", "severity": "HIGH", "outcome": "FAIL"},
    {"rule_id": "DPDP-R002", "severity": "MEDIUM", "outcome": "FAIL"},
    {"rule_id": "DPDP-R003", "severity": "HIGH", "outcome": "FAIL"},
    {"rule_id": "DPDP-R004", "severity": "CRITICAL", "outcome": "FAIL"},
    {"rule_id": "DPDP-R005", "severity": "CRITICAL", "outcome": "FAIL"},
    {"rule_id": "DPDP-R006", "severity": "HIGH", "outcome": "FAIL"},
    {"rule_id": "DPDP-R007", "severity": "MEDIUM", "outcome": "FAIL"},
]

DETECTION_CONFIDENCES = ["MEDIUM", "MEDIUM", "MEDIUM", "HIGH", "MEDIUM", "MEDIUM", "HIGH"]


@pytest.mark.parametrize(
    "score,expected_band",
    [(0, "Low"), (30, "Low"), (31, "Medium"), (60, "Medium"), (61, "High"), (80, "High"), (81, "Critical"), (100, "Critical")],
)
def test_band_boundaries_no_off_by_one(score, expected_band):
    assert band_for_score(score) == expected_band


def test_score_breakdown_sums_exactly_to_score():
    result = compute_risk(SENSITIVE_CATEGORIES, DETECTION_CONFIDENCES, BAD_EVALUATIONS, "Marketing,Sales")
    assert sum(item.points_added for item in result.breakdown) == result.score


def test_bad_dataset_lands_high_or_critical():
    result = compute_risk(SENSITIVE_CATEGORIES, DETECTION_CONFIDENCES, BAD_EVALUATIONS, "Marketing,Sales")
    assert result.band in ("High", "Critical")
    assert 65 <= result.score <= 85


def test_good_context_lands_low():
    good_evaluations = [dict(e, outcome="PASS") for e in BAD_EVALUATIONS]
    result = compute_risk(
        SENSITIVE_CATEGORIES, DETECTION_CONFIDENCES, good_evaluations, "grievance officer: privacy@example.com"
    )
    assert result.band == "Low"


def test_no_pii_and_no_failures_yields_zero_or_near_zero():
    result = compute_risk(set(), [], [], "")
    assert sum(item.points_added for item in result.breakdown) == result.score
    assert result.score == 0
    assert result.band == "Low"


def test_missing_controls_and_severity_only_count_failures():
    mixed_evaluations = [dict(e, outcome="PASS") for e in BAD_EVALUATIONS[:4]] + BAD_EVALUATIONS[4:]
    result = compute_risk(SENSITIVE_CATEGORIES, DETECTION_CONFIDENCES, mixed_evaluations, "Marketing,Sales")
    severity_item = next(item for item in result.breakdown if item.factor == "Rule Severity (Failed Rules)")
    missing_item = next(item for item in result.breakdown if item.factor == "Missing Controls Count")
    assert "3 failed rule(s)" in severity_item.reason
    assert "3 missing control(s)" in missing_item.reason
