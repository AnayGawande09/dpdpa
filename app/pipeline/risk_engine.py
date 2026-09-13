from dataclasses import dataclass, field

# --- Named weight constants (never magic numbers) --------------------------

# Factor 1: inherent sensitivity of the PII categories present in the scan.
PII_SENSITIVITY_WEIGHTS = {
    "Government Identifier": 15,
    "Financial Information": 15,
    "Personal Identifier": 8,
    "Contact Information": 8,
    "Online Identifier": 5,
    "Location": 5,
}
PII_SENSITIVITY_CAP = 30

# Factor 2: DPDP rule severity, summed over only the FAILed evaluations.
SEVERITY_WEIGHTS = {"LOW": 3, "MEDIUM": 6, "HIGH": 10, "CRITICAL": 15}
SEVERITY_CAP = 40

# Factor 3: exposure breadth, parsed from processing_context.access_scope
# as a comma-separated list of who/what can access the data.
EXPOSURE_POINTS_PER_SCOPE_ENTRY = 4
EXPOSURE_CAP = 15

# Factor 4: count of missing controls, i.e. FAILed rule evaluations.
MISSING_CONTROL_POINTS_PER_RULE = 3
MISSING_CONTROL_CAP = 15

# Factor 5: adjustment by average Phase 2 detection confidence — lower
# average confidence pulls the raw score down (less certain the PII is
# really there), higher confidence leaves it unchanged.
CONFIDENCE_SCORE = {"LOW": 0.5, "MEDIUM": 0.75, "HIGH": 1.0}
DEFAULT_CONFIDENCE_SCORE = 0.75

RISK_BANDS = [
    (30, "Low"),
    (60, "Medium"),
    (80, "High"),
    (100, "Critical"),
]


@dataclass
class BreakdownItem:
    factor: str
    points_added: int
    reason: str


@dataclass
class RiskResult:
    score: int
    band: str
    breakdown: list[BreakdownItem] = field(default_factory=list)


def band_for_score(score: int) -> str:
    for upper_bound, band in RISK_BANDS:
        if score <= upper_bound:
            return band
    return "Critical"


def _pii_sensitivity_points(categories: set[str]) -> tuple[int, int]:
    raw = sum(PII_SENSITIVITY_WEIGHTS.get(category, 0) for category in categories)
    return min(raw, PII_SENSITIVITY_CAP), raw


def _severity_points(fail_evaluations: list[dict]) -> tuple[int, int]:
    raw = sum(SEVERITY_WEIGHTS.get(evaluation["severity"], 0) for evaluation in fail_evaluations)
    return min(raw, SEVERITY_CAP), raw


def _exposure_points(access_scope: str | None) -> tuple[int, int]:
    entries = [part.strip() for part in (access_scope or "").split(",") if part.strip()]
    raw = len(entries) * EXPOSURE_POINTS_PER_SCOPE_ENTRY
    return min(raw, EXPOSURE_CAP), len(entries)


def _missing_control_points(fail_evaluations: list[dict]) -> tuple[int, int]:
    raw = len(fail_evaluations) * MISSING_CONTROL_POINTS_PER_RULE
    return min(raw, MISSING_CONTROL_CAP), len(fail_evaluations)


def _average_confidence(detection_confidences: list[str]) -> float:
    if not detection_confidences:
        return 1.0  # no PII detected at all -> no confidence discount to apply
    scores = [CONFIDENCE_SCORE.get(c, DEFAULT_CONFIDENCE_SCORE) for c in detection_confidences]
    return sum(scores) / len(scores)


def compute_risk(
    pii_categories: set[str],
    detection_confidences: list[str],
    rule_evaluations: list[dict],
    access_scope: str | None,
) -> RiskResult:
    fail_evaluations = [e for e in rule_evaluations if e["outcome"] == "FAIL"]

    pii_points, pii_raw = _pii_sensitivity_points(pii_categories)
    severity_points, severity_raw = _severity_points(fail_evaluations)
    exposure_points, exposure_entry_count = _exposure_points(access_scope)
    missing_points, missing_count = _missing_control_points(fail_evaluations)

    raw_total = pii_points + severity_points + exposure_points + missing_points

    avg_confidence = _average_confidence(detection_confidences)
    adjustment = round(raw_total * (avg_confidence - 1))

    score = max(0, min(100, raw_total + adjustment))
    # If clamping to [0, 100] changed the value, fold that into the
    # confidence-adjustment line so the breakdown still sums exactly to score.
    actual_adjustment = score - raw_total

    breakdown = [
        BreakdownItem(
            factor="PII Sensitivity",
            points_added=pii_points,
            reason=(
                f"Detected PII categories {sorted(pii_categories) or ['none']} "
                f"(raw {pii_raw}, capped at {PII_SENSITIVITY_CAP})"
            ),
        ),
        BreakdownItem(
            factor="Rule Severity (Failed Rules)",
            points_added=severity_points,
            reason=(
                f"{len(fail_evaluations)} failed rule(s) with combined severity weight "
                f"{severity_raw} (capped at {SEVERITY_CAP})"
            ),
        ),
        BreakdownItem(
            factor="Exposure Breadth",
            points_added=exposure_points,
            reason=(
                f"{exposure_entry_count} access-scope entr{'y' if exposure_entry_count == 1 else 'ies'} "
                f"(capped at {EXPOSURE_CAP})"
            ),
        ),
        BreakdownItem(
            factor="Missing Controls Count",
            points_added=missing_points,
            reason=f"{missing_count} missing control(s) (capped at {MISSING_CONTROL_CAP})",
        ),
        BreakdownItem(
            factor="Detection Confidence Adjustment",
            points_added=actual_adjustment,
            reason=f"Average PII detection confidence factor {avg_confidence:.2f} applied to raw score {raw_total}",
        ),
    ]

    return RiskResult(score=score, band=band_for_score(score), breakdown=breakdown)
