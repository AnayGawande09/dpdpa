import json

import pytest

from app.pipeline.rules_engine import CONDITION_REGISTRY, RULES_PATH, evaluate_rules, load_rules

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

BAD_CONTEXT = {
    "purpose": "Other",
    "consent_status": "Not available",
    "retention_value": 10,
    "retention_unit": "years",
    "access_scope": "Marketing,Sales",
    "encryption_enabled": False,
    "access_control_enabled": False,
    "notice_status": "Missing",
}

SENSITIVE_CATEGORIES = {"Government Identifier", "Financial Information"}


def test_rules_json_has_6_to_10_rules_with_no_blank_fields():
    rules = load_rules()
    assert 6 <= len(rules) <= 10
    required_fields = {
        "rule_id",
        "source",
        "version",
        "effective_date",
        "category",
        "condition",
        "severity",
        "requirement",
        "remediation",
    }
    for rule in rules:
        assert required_fields.issubset(rule.keys())
        for field in required_fields:
            value = rule[field]
            assert value, f"{rule['rule_id']}.{field} is blank"
            assert "TBD" not in str(value) and "placeholder" not in str(value).lower()


def test_all_required_categories_present():
    rules = load_rules()
    categories = {r["category"] for r in rules}
    assert categories == {
        "Consent",
        "Purpose Limitation",
        "Retention",
        "Access Control",
        "Notice",
        "Rights",
    }


def test_every_rule_condition_is_registered():
    rules = load_rules()
    for rule in rules:
        assert rule["condition"] in CONDITION_REGISTRY, f"{rule['rule_id']} has unregistered condition"


def test_good_context_passes_all_rules_with_sensitive_pii():
    evaluations = evaluate_rules(SENSITIVE_CATEGORIES, GOOD_CONTEXT)
    outcomes = {e.rule_id: e.outcome for e in evaluations}
    assert all(outcome == "PASS" for outcome in outcomes.values()), outcomes


def test_bad_context_fails_all_rules_with_sensitive_pii():
    evaluations = evaluate_rules(SENSITIVE_CATEGORIES, BAD_CONTEXT)
    outcomes = {e.rule_id: e.outcome for e in evaluations}
    assert all(outcome == "FAIL" for outcome in outcomes.values()), outcomes


def test_access_control_and_encryption_pass_without_sensitive_pii():
    # No Government Identifier / Financial Information present -> these two
    # rules should PASS even with encryption/access control both disabled.
    evaluations = evaluate_rules(set(), BAD_CONTEXT)
    outcomes = {e.rule_id: e.outcome for e in evaluations}
    assert outcomes["DPDP-R004"] == "PASS"  # access_control_present_for_sensitive_pii
    assert outcomes["DPDP-R005"] == "PASS"  # encryption_present_for_sensitive_pii


def test_editing_rules_json_changes_evaluator_output_with_zero_code_changes(tmp_path):
    """Prove the evaluator is generic: point it at a modified copy of
    rules.json with one rule removed and confirm the output reflects that,
    with no changes to rules_engine.py's evaluate_rules loop."""
    rules = load_rules()
    trimmed_rules = [r for r in rules if r["rule_id"] != "DPDP-R006"]
    assert len(trimmed_rules) == len(rules) - 1

    tmp_rules_file = tmp_path / "rules.json"
    tmp_rules_file.write_text(json.dumps(trimmed_rules), encoding="utf-8")

    evaluations = evaluate_rules(SENSITIVE_CATEGORIES, GOOD_CONTEXT, rules_path=tmp_rules_file)
    rule_ids = {e.rule_id for e in evaluations}
    assert "DPDP-R006" not in rule_ids
    assert len(evaluations) == len(trimmed_rules)


def test_adding_an_11th_rule_evaluates_with_zero_loop_changes(tmp_path):
    """Prove the evaluator is generic in the other direction: add a new rule
    referencing an already-registered condition and confirm it evaluates,
    again with zero changes to the evaluate_rules loop."""
    rules = load_rules()
    new_rule = {
        "rule_id": "DPDP-TEST-011",
        "source": "DPDP Act 2023",
        "version": "2023",
        "effective_date": "2027-05-13",
        "category": "Notice",
        "condition": "notice_available",
        "severity": "LOW",
        "requirement": "test-only duplicate of the notice rule",
        "remediation": "n/a",
    }
    extended_rules = rules + [new_rule]

    tmp_rules_file = tmp_path / "rules.json"
    tmp_rules_file.write_text(json.dumps(extended_rules), encoding="utf-8")

    evaluations = evaluate_rules(SENSITIVE_CATEGORIES, BAD_CONTEXT, rules_path=tmp_rules_file)
    new_eval = next(e for e in evaluations if e.rule_id == "DPDP-TEST-011")
    assert new_eval.outcome == "FAIL"  # BAD_CONTEXT has notice_status = Missing
    assert len(evaluations) == len(rules) + 1


def test_unregistered_condition_yields_unknown_not_a_crash(tmp_path):
    rules = [
        {
            "rule_id": "DPDP-TEST-UNKNOWN",
            "source": "DPDP Act 2023",
            "version": "2023",
            "effective_date": "2027-05-13",
            "category": "Consent",
            "condition": "some_future_unimplemented_condition",
            "severity": "LOW",
            "requirement": "n/a",
            "remediation": "n/a",
        }
    ]
    tmp_rules_file = tmp_path / "rules.json"
    tmp_rules_file.write_text(json.dumps(rules), encoding="utf-8")

    evaluations = evaluate_rules(SENSITIVE_CATEGORIES, GOOD_CONTEXT, rules_path=tmp_rules_file)
    assert evaluations[0].outcome == "UNKNOWN"
