import re
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd
import spacy

# ---------------------------------------------------------------------------
# Regex detectors
# ---------------------------------------------------------------------------

REGEX_PATTERNS = {
    "regex_email": re.compile(r"^[\w.\-+]+@[\w\-]+\.[a-zA-Z]{2,}$"),
    # normalized (separators stripped) Indian mobile: optional 91/+91 then a 6-9 leading 10-digit number
    "regex_phone": re.compile(r"^(91)?[6-9]\d{9}$"),
    # normalized (separators stripped) 12-digit Aadhaar-like number
    "regex_aadhaar": re.compile(r"^\d{12}$"),
    # 5 letters + 4 digits + 1 letter
    "regex_pan": re.compile(r"^[A-Za-z]{5}\d{4}[A-Za-z]$"),
    "regex_ip": re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$"
        r"|^([0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}$"
    ),
}

# Patterns applied against the value with spaces/hyphens stripped first.
_NORMALIZED_DETECTORS = {"regex_phone", "regex_aadhaar"}

# Column-name keyword heuristics: keyword -> hint detector_type
COLUMN_KEYWORDS = {
    "mail": "regex_email",
    "email": "regex_email",
    "phone": "regex_phone",
    "contact": "regex_phone",
    "mobile": "regex_phone",
    "addr": "spacy_location",
    "address": "spacy_location",
    "dob": "column_heuristic",
    "birth": "column_heuristic",
    "aadhaar": "regex_aadhaar",
    "pan": "regex_pan",
    "ip": "regex_ip",
    "name": "spacy_person",
}

CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass
class Detection:
    field_name: str
    masked_sample: str
    detector_type: str
    confidence: str
    row_ref: int | None = None
    hit_types: set = field(default_factory=set)


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


def mask_value(value: str, detector_type: str) -> str:
    """Mask a raw value before it ever leaves this module."""
    value = str(value)
    if detector_type == "regex_email" and "@" in value:
        local, _, domain = value.partition("@")
        visible = local[:1]
        return f"{visible}{'*' * max(len(local) - 1, 3)}@{domain}"
    digits_only = re.sub(r"\D", "", value)
    if detector_type in ("regex_phone", "regex_aadhaar") and len(digits_only) >= 4:
        return f"{digits_only[:2]}{'*' * (len(digits_only) - 4)}{digits_only[-2:]}"
    if detector_type == "regex_pan" and len(value) >= 4:
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
    if detector_type == "regex_ip":
        parts = value.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.***.***"
        return "***masked-ip***"
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


# ---------------------------------------------------------------------------
# spaCy
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_nlp():
    return spacy.load("en_core_web_sm")


def _spacy_entities(text: str) -> set[str]:
    if not text or not isinstance(text, str):
        return set()
    doc = _get_nlp()(text)
    return {ent.label_ for ent in doc.ents}


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------


_TRAILING_FLOAT_ZERO = re.compile(r"^(\d+)\.0$")


def _clean_stringified_value(value: str) -> str:
    """Undo pandas' float coercion of integer-like columns that contain NaN
    (e.g. a 12-digit Aadhaar-like column becomes "234567890123.0")."""
    match = _TRAILING_FLOAT_ZERO.match(value.strip())
    return match.group(1) if match else value


def _regex_hits(value: str) -> list[str]:
    value = _clean_stringified_value(str(value).strip())
    normalized = re.sub(r"[\s\-]", "", value)
    hits = []
    for detector_type, pattern in REGEX_PATTERNS.items():
        candidate = normalized if detector_type in _NORMALIZED_DETECTORS else value
        if pattern.match(candidate):
            hits.append(detector_type)
    return hits


def _column_keyword_hit(column_name: str) -> str | None:
    lower = column_name.lower()
    for keyword, detector_type in COLUMN_KEYWORDS.items():
        if keyword in lower:
            return detector_type
    return None


def _confidence_from_agreement_count(count: int) -> str:
    if count >= 2:
        return "HIGH"
    if count == 1:
        return "MEDIUM"
    return "LOW"


def detect_column(df: pd.DataFrame, column: str, run_spacy: bool = True) -> Detection | None:
    """Run all detectors against one column and return the single best Detection.

    Confidence is based on how many DISTINCT detector types agree on this
    column: 2+ distinct detectors -> HIGH, exactly 1 -> MEDIUM, only the
    column-name keyword heuristic (no value-level detector) -> LOW.
    """
    series = df[column].dropna().astype(str)
    sample_values = [_clean_stringified_value(v) for v in series.head(50).tolist()]

    value_hit_counts: dict[str, int] = {}
    for value in sample_values:
        for detector_type in _regex_hits(value):
            value_hit_counts[detector_type] = value_hit_counts.get(detector_type, 0) + 1

    if run_spacy and sample_values:
        for value in sample_values[:20]:
            for label in _spacy_entities(value):
                if label == "PERSON":
                    value_hit_counts["spacy_person"] = value_hit_counts.get("spacy_person", 0) + 1
                elif label in ("GPE", "LOC"):
                    value_hit_counts["spacy_location"] = value_hit_counts.get("spacy_location", 0) + 1

    column_hint = _column_keyword_hit(column)
    distinct_detector_types = set(value_hit_counts.keys())

    if not distinct_detector_types and column_hint is None:
        return None

    if distinct_detector_types:
        best_detector_type = max(value_hit_counts, key=value_hit_counts.get)
        agreement_count = len(distinct_detector_types)
        if column_hint and column_hint not in distinct_detector_types:
            agreement_count += 1
        confidence = _confidence_from_agreement_count(agreement_count)
        example_value = sample_values[0] if sample_values else ""
        masked = mask_value(example_value, best_detector_type)
        return Detection(
            field_name=column,
            masked_sample=masked,
            detector_type=best_detector_type,
            confidence=confidence,
            hit_types=distinct_detector_types,
        )

    # Only the column-name heuristic fired — weak signal, LOW confidence.
    example_value = sample_values[0] if sample_values else ""
    masked = mask_value(example_value, "column_heuristic") if example_value else "***"
    return Detection(
        field_name=column,
        masked_sample=masked,
        detector_type="column_heuristic",
        confidence="LOW",
        hit_types={"column_heuristic"},
    )


def detect_pii(df: pd.DataFrame) -> list[Detection]:
    """Run the full detection pipeline over every column of a DataFrame."""
    detections = []
    for column in df.columns:
        detection = detect_column(df, column)
        if detection is not None:
            detections.append(detection)
    return detections
