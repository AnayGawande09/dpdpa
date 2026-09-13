from dataclasses import dataclass

CATEGORY_PERSONAL = "Personal Identifier"
CATEGORY_CONTACT = "Contact Information"
CATEGORY_LOCATION = "Location"
CATEGORY_GOVERNMENT = "Government Identifier"
CATEGORY_FINANCIAL = "Financial Information"
CATEGORY_ONLINE = "Online Identifier"

SOURCE_DETECTOR_MAPPING = "detector_mapping"
SOURCE_FALLBACK_KEYWORD = "fallback_keyword"

# Deterministic detector_type -> (category, subtype) mapping. Every
# detector_type from Phase 2's detection.py must have an entry here.
DETECTOR_TYPE_TO_CLASSIFICATION: dict[str, tuple[str, str]] = {
    "regex_email": (CATEGORY_CONTACT, "Email"),
    "regex_phone": (CATEGORY_CONTACT, "Phone"),
    "regex_aadhaar": (CATEGORY_GOVERNMENT, "Aadhaar-like"),
    "regex_pan": (CATEGORY_FINANCIAL, "PAN-like"),
    "regex_ip": (CATEGORY_ONLINE, "IP Address"),
    "spacy_person": (CATEGORY_PERSONAL, "Full Name"),
    "spacy_location": (CATEGORY_LOCATION, "Free-text"),
}

# Plain keyword -> (category, subtype) match for column_heuristic-only
# detections, i.e. no value-level detector fired, only the column name is
# suggestive. Per SCOPE.md: plain keyword matching, no trained embedding
# model.
FALLBACK_KEYWORD_TO_CLASSIFICATION: dict[str, tuple[str, str]] = {
    "dob": (CATEGORY_PERSONAL, "Date of Birth"),
    "birth": (CATEGORY_PERSONAL, "Date of Birth"),
    "gender": (CATEGORY_PERSONAL, "Demographic Attribute"),
    "name": (CATEGORY_PERSONAL, "Full Name"),
    "mail": (CATEGORY_CONTACT, "Email"),
    "email": (CATEGORY_CONTACT, "Email"),
    "phone": (CATEGORY_CONTACT, "Phone"),
    "contact": (CATEGORY_CONTACT, "Phone"),
    "mobile": (CATEGORY_CONTACT, "Phone"),
    "addr": (CATEGORY_LOCATION, "Free-text"),
    "address": (CATEGORY_LOCATION, "Free-text"),
    "location": (CATEGORY_LOCATION, "Free-text"),
    "city": (CATEGORY_LOCATION, "Free-text"),
    "aadhaar": (CATEGORY_GOVERNMENT, "Aadhaar-like"),
    "passport": (CATEGORY_GOVERNMENT, "Passport-like"),
    "voter": (CATEGORY_GOVERNMENT, "Voter ID-like"),
    "pan": (CATEGORY_FINANCIAL, "PAN-like"),
    "card": (CATEGORY_FINANCIAL, "Payment Card"),
    "account": (CATEGORY_FINANCIAL, "Bank Account"),
    "bank": (CATEGORY_FINANCIAL, "Bank Account"),
    "upi": (CATEGORY_FINANCIAL, "UPI Identifier"),
    "ip": (CATEGORY_ONLINE, "IP Address"),
    "device": (CATEGORY_ONLINE, "Device Identifier"),
    "cookie": (CATEGORY_ONLINE, "Cookie/Session Identifier"),
    "username": (CATEGORY_ONLINE, "Online Handle"),
}

DEFAULT_FALLBACK_CATEGORY = (CATEGORY_PERSONAL, "Uncategorized")


@dataclass
class Classification:
    category: str
    subtype: str
    confidence: str
    source: str


def classify_detection(detector_type: str, field_name: str, detection_confidence: str) -> Classification:
    """Classify one PII detection into the DPDP taxonomy.

    Deterministic lookup for known detector_types. For column_heuristic-only
    detections (no value-level detector fired), fall back to a plain
    keyword-similarity match against the column name, at LOW confidence.
    """
    if detector_type in DETECTOR_TYPE_TO_CLASSIFICATION:
        category, subtype = DETECTOR_TYPE_TO_CLASSIFICATION[detector_type]
        return Classification(
            category=category,
            subtype=subtype,
            confidence=detection_confidence,
            source=SOURCE_DETECTOR_MAPPING,
        )

    lower_field_name = field_name.lower()
    for keyword, (category, subtype) in FALLBACK_KEYWORD_TO_CLASSIFICATION.items():
        if keyword in lower_field_name:
            return Classification(
                category=category,
                subtype=subtype,
                confidence="LOW",
                source=SOURCE_FALLBACK_KEYWORD,
            )

    category, subtype = DEFAULT_FALLBACK_CATEGORY
    return Classification(category=category, subtype=subtype, confidence="LOW", source=SOURCE_FALLBACK_KEYWORD)
