import json
from dataclasses import dataclass
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.json"

# Retention beyond this many days is treated as excessive for DPDP-R003.
RETENTION_EXCESSIVE_THRESHOLD_DAYS = 3 * 365

RETENTION_UNIT_TO_DAYS = {"days": 1, "months": 30, "years": 365}

SENSITIVE_PII_CATEGORIES = {"Government Identifier", "Financial Information"}

# Free-text keywords in access_scope that count as evidence of a rights /
# grievance-redressal channel.
RIGHTS_MECHANISM_KEYWORDS = ("grievance", "dpo", "privacy", "support", "redress")

# Data minimization (DPDP-R008): which PII categories are actually necessary
# for each declared purpose. Anything detected outside this set is flagged
# as an unnecessary field. Deliberately left blank for "Other" — a purpose
# too generic to determine necessity against (consistent with DPDP-R002
# already flagging "Other" as insufficiently specific).
NECESSARY_CATEGORIES_BY_PURPOSE: dict[str, set[str]] = {
    "Marketing": {"Contact Information", "Personal Identifier", "Location"},
    "Customer Support": {"Contact Information", "Personal Identifier"},
    "Analytics": {"Location", "Online Identifier"},
    "Legal/Compliance": {
        "Personal Identifier",
        "Contact Information",
        "Government Identifier",
        "Financial Information",
    },
    "Other": set(),
}


def necessary_categories_for_purpose(purpose: str) -> set[str]:
    return NECESSARY_CATEGORIES_BY_PURPOSE.get(purpose, set())


def unnecessary_categories_for_purpose(categories: set[str], purpose: str) -> set[str]:
    return categories - necessary_categories_for_purpose(purpose)


@dataclass
class RuleOutcome:
    outcome: str  # PASS | FAIL | UNKNOWN
    evidence_field: str


def check_consent_status_available(categories: set[str], context: dict) -> RuleOutcome:
    if context.get("consent_status") == "Available":
        return RuleOutcome("PASS", "consent_status")
    return RuleOutcome("FAIL", "consent_status")


def check_purpose_is_specific(categories: set[str], context: dict) -> RuleOutcome:
    if context.get("purpose") == "Other":
        return RuleOutcome("FAIL", "purpose")
    return RuleOutcome("PASS", "purpose")


def check_retention_within_limit(categories: set[str], context: dict) -> RuleOutcome:
    value = context.get("retention_value")
    unit = context.get("retention_unit")
    if value is None or unit is None:
        return RuleOutcome("UNKNOWN", "retention_value")
    days = value * RETENTION_UNIT_TO_DAYS.get(unit, 0)
    if value <= 0 or days > RETENTION_EXCESSIVE_THRESHOLD_DAYS:
        return RuleOutcome("FAIL", "retention_value")
    return RuleOutcome("PASS", "retention_value")


def check_access_control_present_for_sensitive_pii(categories: set[str], context: dict) -> RuleOutcome:
    has_sensitive_pii = bool(categories & SENSITIVE_PII_CATEGORIES)
    if not has_sensitive_pii:
        return RuleOutcome("PASS", "access_control_enabled")
    if context.get("access_control_enabled"):
        return RuleOutcome("PASS", "access_control_enabled")
    return RuleOutcome("FAIL", "access_control_enabled")


def check_encryption_present_for_sensitive_pii(categories: set[str], context: dict) -> RuleOutcome:
    has_sensitive_pii = bool(categories & SENSITIVE_PII_CATEGORIES)
    if not has_sensitive_pii:
        return RuleOutcome("PASS", "encryption_enabled")
    if context.get("encryption_enabled"):
        return RuleOutcome("PASS", "encryption_enabled")
    return RuleOutcome("FAIL", "encryption_enabled")


def check_notice_available(categories: set[str], context: dict) -> RuleOutcome:
    if context.get("notice_status") == "Available":
        return RuleOutcome("PASS", "notice_status")
    return RuleOutcome("FAIL", "notice_status")


def check_rights_mechanism_evidenced(categories: set[str], context: dict) -> RuleOutcome:
    access_scope = (context.get("access_scope") or "").lower()
    if any(keyword in access_scope for keyword in RIGHTS_MECHANISM_KEYWORDS):
        return RuleOutcome("PASS", "access_scope")
    return RuleOutcome("FAIL", "access_scope")


def check_data_minimization_satisfied(categories: set[str], context: dict) -> RuleOutcome:
    purpose = context.get("purpose")
    unnecessary = unnecessary_categories_for_purpose(categories, purpose)
    if unnecessary:
        return RuleOutcome("FAIL", "data_minimization")
    return RuleOutcome("PASS", "data_minimization")


# The registry maps each rules.json "condition" string to its check function.
# ---------------------------------------------------------------------------
# To add an 11th rule: (1) append a new object to app/rules/rules.json with a
# new "condition" string, (2) write a new check_* function above with the
# signature (categories: set[str], context: dict) -> RuleOutcome, and
# (3) register its condition string -> function below. The evaluate_rules
# loop itself never changes.
CONDITION_REGISTRY = {
    "consent_status_available": check_consent_status_available,
    "purpose_is_specific": check_purpose_is_specific,
    "retention_within_limit": check_retention_within_limit,
    "access_control_present_for_sensitive_pii": check_access_control_present_for_sensitive_pii,
    "encryption_present_for_sensitive_pii": check_encryption_present_for_sensitive_pii,
    "notice_available": check_notice_available,
    "rights_mechanism_evidenced": check_rights_mechanism_evidenced,
    "data_minimization_satisfied": check_data_minimization_satisfied,
}


def load_rules(rules_path: Path = RULES_PATH) -> list[dict]:
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class RuleEvaluation:
    rule_id: str
    category: str
    severity: str
    outcome: str
    evidence_field: str


def evaluate_rules(categories: set[str], context: dict, rules_path: Path = RULES_PATH) -> list[RuleEvaluation]:
    """Evaluate every rule in rules.json against this scan's PII categories
    and processing context. Generic loop — no rule-specific branching here;
    all rule-specific logic lives in the registered check_* functions."""
    rules = load_rules(rules_path)
    evaluations = []
    for rule in rules:
        check_fn = CONDITION_REGISTRY.get(rule["condition"])
        if check_fn is None:
            result = RuleOutcome("UNKNOWN", "condition")
        else:
            result = check_fn(categories, context)
        evaluations.append(
            RuleEvaluation(
                rule_id=rule["rule_id"],
                category=rule["category"],
                severity=rule["severity"],
                outcome=result.outcome,
                evidence_field=result.evidence_field,
            )
        )
    return evaluations
