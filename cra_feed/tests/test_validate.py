"""Unit tests for cra_feed.validate — JSON Schema validation of the CRA feed."""

from __future__ import annotations

import copy

import jsonschema
import pytest

from cra_feed.validate import validate_feed

# ---------------------------------------------------------------------------
# Minimal valid feed fixture
# ---------------------------------------------------------------------------

VALID_FEED: dict = {
    "schema_version": "1.0",
    "jurisdiction": "CA",
    "effective_date": "2026-01-01",
    "published_at": "2026-04-18T06:00:00Z",
    "source_urls": [
        "https://www.canada.ca/en/revenue-agency/services/forms-publications/payroll/t4127-payroll-deductions-formulas/t4127-jan-2026-computer-programs.html",
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/payroll-deductions-contributions/canada-pension-plan-cpp/cpp-contribution-rates-maximums-exemptions.html",
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/payroll-deductions-contributions/employment-insurance-ei/ei-premium-rates-maximums.html",
    ],
    "federal": {
        "bpaf": {"min": 14538.0, "max": 16452.0},
        "k1_rate": 0.14,
        "tax_brackets": [
            {"up_to": 58523.0, "rate": 0.14},
            {"up_to": 117045.0, "rate": 0.205},
            {"up_to": 181440.0, "rate": 0.26},
            {"up_to": 258482.0, "rate": 0.29},
            {"up_to": None, "rate": 0.33},
        ],
    },
    "cpp": {"rate": 0.0595, "ympe": 74600.0, "basic_exemption": 3500.0},
    "cpp2": {"rate": 0.04, "yampe": 85000.0},
    "ei": {"rate": 0.0163, "max_insurable_earnings": 68900.0},
    "provinces": {
        "ON": {
            "bpa": 11865.0,
            "tax_brackets": [
                {"up_to": 51446.0, "rate": 0.0505},
                {"up_to": 102894.0, "rate": 0.0915},
                {"up_to": 150000.0, "rate": 0.1116},
                {"up_to": 220000.0, "rate": 0.1216},
                {"up_to": None, "rate": 0.1316},
            ],
        },
        "BC": {
            "bpa": 11981.0,
            "tax_brackets": [
                {"up_to": 45654.0, "rate": 0.0506},
                {"up_to": 91310.0, "rate": 0.077},
                {"up_to": None, "rate": 0.105},
            ],
        },
    },
    "checksum_sha256": "a" * 64,
}


# ---------------------------------------------------------------------------
# Happy-path test
# ---------------------------------------------------------------------------

class TestValidFeed:
    def test_valid_feed_passes(self):
        """A fully-populated valid feed dict must pass validation."""
        validate_feed(VALID_FEED)  # should not raise


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------

class TestMissingRequiredField:
    def test_missing_federal(self):
        feed = copy.deepcopy(VALID_FEED)
        del feed["federal"]
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_missing_cpp(self):
        feed = copy.deepcopy(VALID_FEED)
        del feed["cpp"]
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_missing_schema_version(self):
        feed = copy.deepcopy(VALID_FEED)
        del feed["schema_version"]
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_missing_checksum(self):
        feed = copy.deepcopy(VALID_FEED)
        del feed["checksum_sha256"]
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestWrongType:
    def test_cpp_rate_as_string(self):
        """cpp.rate must be a number, not a string."""
        feed = copy.deepcopy(VALID_FEED)
        feed["cpp"]["rate"] = "0.0595"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_effective_date_as_number(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["effective_date"] = 20260101
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_source_urls_not_array(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["source_urls"] = "https://example.com"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestOutOfRangeRate:
    def test_cpp_rate_above_one(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["cpp"]["rate"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_ei_rate_negative(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["ei"]["rate"] = -0.01
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_federal_bracket_rate_above_one(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["federal"]["tax_brackets"][0]["rate"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestInvalidProvinceKey:
    def test_qc_province_rejected(self):
        """QC is explicitly excluded from the schema."""
        feed = copy.deepcopy(VALID_FEED)
        feed["provinces"]["QC"] = {
            "bpa": 17183.0,
            "tax_brackets": [
                {"up_to": 51780.0, "rate": 0.14},
                {"up_to": None, "rate": 0.19},
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_unknown_province_rejected(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["provinces"]["XX"] = {
            "bpa": 10000.0,
            "tax_brackets": [
                {"up_to": 50000.0, "rate": 0.10},
                {"up_to": None, "rate": 0.15},
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestLastFederalBracketNotNull:
    def test_all_brackets_have_numeric_up_to(self):
        """If no bracket has up_to: null the schema must reject the feed."""
        feed = copy.deepcopy(VALID_FEED)
        # Replace the last bracket's up_to from null to a numeric value.
        feed["federal"]["tax_brackets"][-1]["up_to"] = 999999.0
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestUnknownTopLevelField:
    def test_extra_top_level_field_rejected(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["unknown_extra_field"] = "should not be here"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestChecksumFormat:
    def test_checksum_wrong_length(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["checksum_sha256"] = "abc123"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_checksum_uppercase_rejected(self):
        """Checksum must be lowercase hex only."""
        feed = copy.deepcopy(VALID_FEED)
        feed["checksum_sha256"] = "A" * 64
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_checksum_mixed_case_rejected(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["checksum_sha256"] = "aAbBcC" + "a" * 58
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestSchemaVersionAndJurisdiction:
    def test_wrong_schema_version(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["schema_version"] = "2.0"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_wrong_jurisdiction(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["jurisdiction"] = "US"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestSourceUrls:
    def test_empty_source_urls_rejected(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["source_urls"] = []
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)


class TestDateFormats:
    def test_effective_date_wrong_format(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["effective_date"] = "2026/01/01"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)

    def test_published_at_wrong_format(self):
        feed = copy.deepcopy(VALID_FEED)
        feed["published_at"] = "2026-04-18 06:00:00"
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)
