import pytest

from app.pipeline.classification import (
    DETECTOR_TYPE_TO_CLASSIFICATION,
    SOURCE_DETECTOR_MAPPING,
    SOURCE_FALLBACK_KEYWORD,
    classify_detection,
)
from app.pipeline.detection import REGEX_PATTERNS

ALL_DETECTOR_TYPES = set(REGEX_PATTERNS.keys()) | {"spacy_person", "spacy_location"}


def test_mapping_covers_every_detector_type_from_phase_2():
    assert ALL_DETECTOR_TYPES.issubset(DETECTOR_TYPE_TO_CLASSIFICATION.keys())


def test_all_six_taxonomy_categories_are_reachable():
    categories = {cat for cat, _ in DETECTOR_TYPE_TO_CLASSIFICATION.values()}
    assert categories == {
        "Personal Identifier",
        "Contact Information",
        "Location",
        "Government Identifier",
        "Financial Information",
        "Online Identifier",
    }


@pytest.mark.parametrize(
    "detector_type,expected_category",
    [
        ("regex_email", "Contact Information"),
        ("regex_phone", "Contact Information"),
        ("regex_aadhaar", "Government Identifier"),
        ("regex_pan", "Financial Information"),
        ("regex_ip", "Online Identifier"),
        ("spacy_person", "Personal Identifier"),
        ("spacy_location", "Location"),
    ],
)
def test_detector_mapping_classification(detector_type, expected_category):
    result = classify_detection(detector_type, "some_field", "HIGH")
    assert result.category == expected_category
    assert result.source == SOURCE_DETECTOR_MAPPING
    assert result.confidence == "HIGH"


def test_fallback_path_for_column_heuristic_dob():
    result = classify_detection("column_heuristic", "dob", "LOW")
    assert result.category == "Personal Identifier"
    assert result.source == SOURCE_FALLBACK_KEYWORD


def test_fallback_path_for_ambiguous_messy_columns():
    result = classify_detection("column_heuristic", "cust_email", "LOW")
    assert result.category == "Contact Information"
    result2 = classify_detection("column_heuristic", "contact_no", "LOW")
    assert result2.category == "Contact Information"


def test_fallback_default_for_unrecognized_column_name():
    result = classify_detection("column_heuristic", "xyzzy_field", "LOW")
    assert result.source == SOURCE_FALLBACK_KEYWORD
    assert result.category  # non-empty, sensible default
