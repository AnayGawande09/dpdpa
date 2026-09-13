import pytest

from app.pipeline.detection import REGEX_PATTERNS, _regex_hits, mask_value


# --- Regex detectors, tested directly against real sample values ---------

def test_regex_email_matches_real_value():
    assert "regex_email" in _regex_hits("ravi.kumar@gmail.com")


def test_regex_phone_matches_real_indian_formats():
    for value in ["9876543210", "98-7654-3210", "91234 56780", "90123-45678"]:
        assert "regex_phone" in _regex_hits(value), value


def test_regex_aadhaar_matches_12_digit_value():
    assert "regex_aadhaar" in _regex_hits("234567890123")


def test_regex_aadhaar_matches_pandas_float_coerced_value():
    # pandas turns a NaN-containing integer-like column into "...123.0"
    assert "regex_aadhaar" in _regex_hits("234567890123.0")


def test_regex_pan_matches_real_value():
    assert "regex_pan" in _regex_hits("ABCDE1234F")


def test_regex_ip_matches_ipv4():
    assert "regex_ip" in _regex_hits("192.168.1.10")


def test_all_five_detectors_registered():
    assert set(REGEX_PATTERNS.keys()) == {
        "regex_email",
        "regex_phone",
        "regex_aadhaar",
        "regex_pan",
        "regex_ip",
    }


# --- Masking ---------------------------------------------------------------

def test_mask_email_hides_local_part():
    masked = mask_value("ravi.kumar@gmail.com", "regex_email")
    assert masked.endswith("@gmail.com")
    assert "ravi.kumar" not in masked


def test_mask_phone_hides_middle_digits():
    masked = mask_value("9876543210", "regex_phone")
    assert masked != "9876543210"
    assert "*" in masked


def test_mask_never_returns_raw_pan():
    masked = mask_value("ABCDE1234F", "regex_pan")
    assert masked != "ABCDE1234F"
    assert "*" in masked
