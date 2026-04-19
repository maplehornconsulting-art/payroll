# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Unit tests for CRA Tax Update connector logic.

These tests exercise pure-Python helpers (no Odoo ORM required).
The _prov_blob module is loaded directly via importlib to avoid triggering
the Odoo import chain in the parent package.
"""

from __future__ import annotations

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
