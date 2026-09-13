from dataclasses import dataclass

from app.pipeline.rules_engine import unnecessary_categories_for_purpose

# Rules whose finding should only cite the sensitive PII fields it actually
# concerns, rather than every detected field in the dataset.
SENSITIVE_ONLY_RULE_IDS = {"DPDP-R004", "DPDP-R005"}
SENSITIVE_CATEGORIES = {"Government Identifier", "Financial Information"}

# The data minimization rule cites only the fields that are unnecessary for
# the declared purpose, not every detected field or a fixed category set.
DATA_MINIMIZATION_RULE_ID = "DPDP-R008"

# Human-readable label for the control an evidence_field represents. Keyed
# on evidence_field (already recorded on the rule evaluation) rather than
# rule_id, so it stays correct even if rules.json is edited.
MISSING_CONTROL_BY_EVIDENCE_FIELD = {
    "consent_status": "Recorded Consent",
    "purpose": "a Specific Declared Purpose",
    "retention_value": "a Bounded Retention Period",
    "access_control_enabled": "Access Control",
    "encryption_enabled": "Encryption",
    "notice_status": "Data Principal Notice",
    "access_scope": "an Evidenced Rights/Grievance Mechanism",
    "data_minimization": "Data Minimization (unnecessary fields should be removed)",
}
DEFAULT_MISSING_CONTROL = "a Required Control"


@dataclass
class Finding:
    category: str
    affected_fields: list[str]
    purpose: str
    missing_control: str
    rule_id: str
    evidence: str
    severity: str
    explanation: str


def _affected_fields_for_rule(rule_id: str, category_to_fields: dict[str, list[str]], purpose: str) -> list[str]:
    if rule_id == DATA_MINIMIZATION_RULE_ID:
        unnecessary_categories = unnecessary_categories_for_purpose(set(category_to_fields.keys()), purpose)
        fields = []
        for category in unnecessary_categories:
            fields.extend(category_to_fields.get(category, []))
        return fields
    if rule_id in SENSITIVE_ONLY_RULE_IDS:
        fields = []
        for category in SENSITIVE_CATEGORIES:
            fields.extend(category_to_fields.get(category, []))
        return fields
    # Dataset-wide obligations (consent, purpose, retention, notice, rights)
    # concern every detected PII field, not just a subset.
    all_fields = []
    for fields in category_to_fields.values():
        all_fields.extend(fields)
    return all_fields


def generate_findings(
    fail_evaluations: list[dict],
    category_to_fields: dict[str, list[str]],
    purpose: str,
    rules_by_id: dict[str, dict],
) -> list[Finding]:
    """Turn every FAILed rule evaluation into a finding with a templated
    explanation. Templated, not LLM-generated — this is the seam where a
    real LLM call could later produce richer natural-language explanations;
    no such call is wired up in this phase."""
    findings = []
    for evaluation in fail_evaluations:
        rule = rules_by_id.get(evaluation["rule_id"], {})
        affected_fields = _affected_fields_for_rule(evaluation["rule_id"], category_to_fields, purpose)
        missing_control = MISSING_CONTROL_BY_EVIDENCE_FIELD.get(
            evaluation["evidence_field"], DEFAULT_MISSING_CONTROL
        )
        affected_fields_str = ", ".join(affected_fields) if affected_fields else "personal data in this dataset"
        remediation = rule.get("remediation", "review and remediate this gap")

        explanation = (
            f"This was flagged because {affected_fields_str} is processed for {purpose} "
            f"without {missing_control}. Recommended action: {remediation} (rule {evaluation['rule_id']})."
        )

        findings.append(
            Finding(
                category=evaluation["category"],
                affected_fields=affected_fields,
                purpose=purpose,
                missing_control=missing_control,
                rule_id=evaluation["rule_id"],
                evidence=evaluation["evidence_field"],
                severity=evaluation["severity"],
                explanation=explanation,
            )
        )
    return findings
