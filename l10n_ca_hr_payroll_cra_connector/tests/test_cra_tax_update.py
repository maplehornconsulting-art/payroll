# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Unit tests for CRA Tax Update connector logic.

These tests exercise pure-Python helpers (no Odoo ORM required).
The _prov_blob module is loaded directly via importlib to avoid triggering
the Odoo import chain in the parent package.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

import pytest


def _load_build_prov_blob():
    """Load _build_prov_blob from _prov_blob.py without importing the Odoo package."""
    path = pathlib.Path(__file__).parent.parent / "models" / "_prov_blob.py"
    spec = importlib.util.spec_from_file_location("_prov_blob", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_prov_blob


# Cache the function at module level so it is loaded once per test session.
_build_prov_blob = _load_build_prov_blob()


# ---------------------------------------------------------------------------
# _build_prov_blob tests
# ---------------------------------------------------------------------------

class TestBuildProvBlob:
    """Unit tests for _build_prov_blob() — the pure consolidation function."""

    _PROVINCES = {
        "ON": {
            "bpa": 12989,
            "tax_brackets": [
                {"up_to": 53891, "rate": 0.0505},
                {"up_to": 107785, "rate": 0.0915},
                {"up_to": 150000, "rate": 0.1116},
                {"up_to": 220000, "rate": 0.1216},
                {"up_to": None, "rate": 0.1316},
            ],
            "surtax": [[5818, 0.20], [7446, 0.36]],
        },
        "AB": {
            "bpa": 22769,
            "tax_brackets": [
                {"up_to": 61200, "rate": 0.08},
                {"up_to": 154259, "rate": 0.10},
                {"up_to": 185111, "rate": 0.12},
                {"up_to": 246813, "rate": 0.13},
                {"up_to": 370220, "rate": 0.14},
                {"up_to": None, "rate": 0.15},
            ],
            "surtax": [],
        },
        "QC": {
            "bpa": 99999,
            "tax_brackets": [{"up_to": None, "rate": 0.15}],
            "surtax": [],
        },
    }

    @pytest.fixture(scope="class")
    def blob(self):
        return _build_prov_blob(self._PROVINCES)

    def test_qc_excluded(self, blob):
        """QC is not in the supported set and must be excluded."""
        assert "QC" not in blob

    def test_on_present(self, blob):
        assert "ON" in blob

    def test_ab_present(self, blob):
        assert "AB" in blob

    def test_on_bpa_integer(self, blob):
        """Whole-number BPA must be serialised without trailing .0."""
        assert blob["ON"]["bpa"] == 12989
        assert isinstance(blob["ON"]["bpa"], int)

    def test_ab_bpa_integer(self, blob):
        assert blob["AB"]["bpa"] == 22769
        assert isinstance(blob["AB"]["bpa"], int)

    def test_on_top_bracket_zero(self, blob):
        """Open-ended top bracket must encode up_to as 0, not null."""
        top = blob["ON"]["brackets"][-1]
        assert top[0] == 0

    def test_ab_top_bracket_zero(self, blob):
        top = blob["AB"]["brackets"][-1]
        assert top[0] == 0

    def test_on_bracket_count(self, blob):
        assert len(blob["ON"]["brackets"]) == 5

    def test_ab_bracket_count(self, blob):
        assert len(blob["AB"]["brackets"]) == 6

    def test_on_bracket_thresholds(self, blob):
        thresholds = [b[0] for b in blob["ON"]["brackets"]]
        assert thresholds == [53891, 107785, 150000, 220000, 0]

    def test_on_bracket_rates(self, blob):
        rates = [b[1] for b in blob["ON"]["brackets"]]
        assert rates == pytest.approx([0.0505, 0.0915, 0.1116, 0.1216, 0.1316])

    def test_on_surtax(self, blob):
        assert blob["ON"]["surtax"] == [[5818, 0.20], [7446, 0.36]]

    def test_ab_surtax_empty(self, blob):
        assert blob["AB"]["surtax"] == []

    def test_on_surtax_threshold_integer(self, blob):
        """Whole-number surtax thresholds must be integers, not floats."""
        assert isinstance(blob["ON"]["surtax"][0][0], int)
        assert isinstance(blob["ON"]["surtax"][1][0], int)

    def test_json_roundtrip(self, blob):
        """JSON serialisation and parse must produce identical structure."""
        serialised = json.dumps(blob, indent=2, ensure_ascii=False, sort_keys=True)
        parsed = json.loads(serialised)
        assert parsed["ON"]["bpa"] == 12989
        assert parsed["ON"]["surtax"] == [[5818, 0.2], [7446, 0.36]]
        assert parsed["AB"]["surtax"] == []
        assert parsed["ON"]["brackets"][-1][0] == 0

    def test_no_decimal_on_bpa_in_json(self, blob):
        """When serialised to JSON, integer BPA must not have a decimal point."""
        serialised = json.dumps(blob, indent=2, ensure_ascii=False, sort_keys=True)
        assert '"bpa": 12989' in serialised
        assert '"bpa": 12989.0' not in serialised

    def test_provinces_with_missing_surtax_key(self):
        """Province data without a 'surtax' key must default to []."""
        provinces = {
            "BC": {
                "bpa": 11981,
                "tax_brackets": [
                    {"up_to": 45654, "rate": 0.0506},
                    {"up_to": None, "rate": 0.077},
                ],
                # no "surtax" key — simulates pre-surtax feed data
            }
        }
        blob = _build_prov_blob(provinces)
        assert blob["BC"]["surtax"] == []


# ---------------------------------------------------------------------------
# End-to-end: connector blob flows into PROV_TAX rule logic
# ---------------------------------------------------------------------------
# These tests verify that the JSON produced by _build_prov_blob is directly
# consumable by the new PROV_TAX rule logic (which reads the 'brackets' and
# 'surtax' keys produced by the connector, normalising at read-time).


def _prov_tax_from_blob(blob_literal: str, province: str, gross: float, periods: int) -> float:
    """Replicate PROV_TAX rule logic reading from a connector-produced blob."""
    annual_income = gross * periods

    PROV_RAW = ast.literal_eval(blob_literal)

    cfg_raw = PROV_RAW.get(province) or PROV_RAW.get('ON') or {}
    cfg = {
        'b':   cfg_raw.get('brackets', []),
        'bpa': cfg_raw.get('bpa', 0),
        'st':  cfg_raw.get('surtax', []),
    }

    prov_brackets = []
    for br in cfg['b']:
        t = br[0] if br[0] != 0 else float('inf')
        prov_brackets.append((t, br[1]))

    if not prov_brackets:
        return 0.0

    tax = 0.0
    prev_bracket = 0.0
    for bracket, rate in prov_brackets:
        taxable_in_bracket = min(annual_income, bracket) - prev_bracket
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_bracket = bracket
        if annual_income <= bracket:
            break

    prov_credit = cfg['bpa'] * prov_brackets[0][1]
    basic_provincial_tax = max(tax - prov_credit, 0.0)

    surtax = 0.0
    for s in cfg['st']:
        if basic_provincial_tax > s[0]:
            surtax += (basic_provincial_tax - s[0]) * s[1]

    return round(-((basic_provincial_tax + surtax) / periods), 2)


class TestConnectorBlobFlowsIntoProcTaxRule:
    """End-to-end: _build_prov_blob output consumed by PROV_TAX rule logic."""

    _PROVINCES_2027 = {
        "NS": {
            "bpa": 12500,  # bumped vs 2026 (11932) — synthetic 2027
            "tax_brackets": [
                {"up_to": 32000, "rate": 0.0879},
                {"up_to": 64000, "rate": 0.1495},
                {"up_to": 100000, "rate": 0.1667},
                {"up_to": 160000, "rate": 0.175},
                {"up_to": None, "rate": 0.21},
            ],
            "surtax": [],
        },
        "ON": {
            "bpa": 13500,
            "tax_brackets": [
                {"up_to": 55000, "rate": 0.0505},
                {"up_to": 110000, "rate": 0.0915},
                {"up_to": 155000, "rate": 0.1116},
                {"up_to": 225000, "rate": 0.1216},
                {"up_to": None, "rate": 0.1316},
            ],
            "surtax": [[5818, 0.20], [7446, 0.36]],
        },
    }

    @pytest.fixture(scope="class")
    def blob_literal(self):
        blob = _build_prov_blob(self._PROVINCES_2027)
        return repr(blob)

    def test_blob_is_valid_python_literal(self, blob_literal):
        """Connector blob must be a valid Python literal (ast.literal_eval-safe)."""
        parsed = ast.literal_eval(blob_literal)
        assert isinstance(parsed, dict)

    def test_blob_uses_brackets_key(self, blob_literal):
        """Connector blob keys are 'brackets', 'bpa', 'surtax' (not 'b'/'st')."""
        parsed = ast.literal_eval(blob_literal)
        assert "brackets" in parsed["NS"]
        assert "bpa" in parsed["NS"]
        assert "surtax" in parsed["NS"]

    def test_rule_reads_connector_bpa(self, blob_literal):
        """After connector runs, PROV_TAX reflects the new BPA from the blob."""
        gross = 1203.13
        periods = 52
        result_2027 = _prov_tax_from_blob(blob_literal, "NS", gross, periods)
        # With bpa=12500 (> 2026 baseline 11932) → less withholding
        result_2026 = _prov_tax_from_blob(
            repr(_build_prov_blob({"NS": {
                "bpa": 11932,
                "tax_brackets": [
                    {"up_to": 30995, "rate": 0.0879},
                    {"up_to": 61991, "rate": 0.1495},
                    {"up_to": 97417, "rate": 0.1667},
                    {"up_to": 157124, "rate": 0.175},
                    {"up_to": None, "rate": 0.21},
                ],
                "surtax": [],
            }})),
            "NS", gross, periods,
        )
        assert result_2027 > result_2026, (
            "Higher 2027 BPA should reduce PROV_TAX withholding vs 2026 baseline"
        )

    def test_on_surtax_flows_through(self, blob_literal):
        """ON surtax from connector blob is applied correctly in rule logic."""
        # ON income high enough to trigger surtax
        gross_high = 200000 / 52
        result = _prov_tax_from_blob(blob_literal, "ON", gross_high, 52)
        assert result < 0, "ON PROV_TAX at high income should be negative"


# ---------------------------------------------------------------------------
# Regression: repr() serialisation is safe_eval / ast.literal_eval compatible
# ---------------------------------------------------------------------------


class TestReprSerialisation:
    """repr() of prov blob must not contain JSON-only tokens and must round-trip."""

    _PROVINCES = {
        "ON": {
            "bpa": 12989,
            "tax_brackets": [
                {"up_to": 53891, "rate": 0.0505},
                {"up_to": None, "rate": 0.1316},
            ],
            "surtax": [[5818, 0.20], [7446, 0.36]],
        },
        "AB": {
            "bpa": 22769,
            "tax_brackets": [
                {"up_to": 61200, "rate": 0.08},
                {"up_to": None, "rate": 0.15},
            ],
            "surtax": [],
        },
    }

    @pytest.fixture(scope="class")
    def blob(self):
        return _build_prov_blob(self._PROVINCES)

    @pytest.fixture(scope="class")
    def literal(self, blob):
        return repr(blob)

    def test_no_json_null_token(self, literal):
        """repr() must not contain the JSON 'null' token."""
        assert "null" not in literal, f"'null' found in repr output: {literal!r}"

    def test_no_json_true_token(self, literal):
        """repr() must not contain the JSON 'true' token."""
        assert "true" not in literal, f"'true' found in repr output: {literal!r}"

    def test_no_json_false_token(self, literal):
        """repr() must not contain the JSON 'false' token."""
        assert "false" not in literal, f"'false' found in repr output: {literal!r}"

    def test_ast_literal_eval_roundtrip(self, blob, literal):
        """ast.literal_eval(repr(blob)) must recover the original dict exactly."""
        recovered = ast.literal_eval(literal)
        assert recovered == blob

    def test_repr_literal_passes_ast_literal_eval(self, literal):
        """ast.literal_eval must not raise on the repr() string."""
        result = ast.literal_eval(literal)
        assert isinstance(result, dict)

    def test_open_ended_bracket_is_zero_not_none(self, blob):
        """The open-ended bracket encodes as 0 (not None) so no null appears."""
        top_on = blob["ON"]["brackets"][-1]
        assert top_on[0] == 0, "Open-ended bracket must be 0, not None"
