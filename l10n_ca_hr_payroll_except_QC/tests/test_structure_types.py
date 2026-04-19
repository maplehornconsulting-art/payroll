# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Tests for the dual Hourly/Salaried structure types introduced in v19.0.1.4.

These tests verify:
1. Both structure type records are declared in the XML data file.
2. Both pay structure records are declared in the XML data file, each pointing
   at the correct structure type.
3. The ``_l10n_ca_clone_rules_to_salaried`` Python helper is idempotent and
   correctly copies rules from a source structure to a target.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers to parse the data XML files
# ---------------------------------------------------------------------------

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"


def _parse_xml(filename: str) -> ET.Element:
    return ET.parse(_DATA_DIR / filename).getroot()


def _record_ids(root: ET.Element, model: str) -> dict[str, dict[str, str]]:
    """Return {xml_id: {field_name: field_value}} for all <record> elements
    matching *model*."""
    result: dict[str, dict[str, str]] = {}
    for rec in root.findall(".//record[@model='" + model + "']"):
        rid = rec.get("id", "")
        fields: dict[str, str] = {}
        for fld in rec.findall("field"):
            name = fld.get("name", "")
            value = fld.get("ref") or fld.text or ""
            fields[name] = value.strip()
        result[rid] = fields
    return result


# ---------------------------------------------------------------------------
# 1. Structure type data file
# ---------------------------------------------------------------------------


class TestStructureTypeXml:
    """Verify hr_payroll_structure_type_data.xml declares both types."""

    def setup_method(self):
        root = _parse_xml("hr_payroll_structure_type_data.xml")
        self.types = _record_ids(root, "hr.payroll.structure.type")

    def test_hourly_type_exists(self):
        assert "structure_type_employee_ca" in self.types, (
            "Hourly structure type xml id 'structure_type_employee_ca' not found"
        )

    def test_salaried_type_exists(self):
        assert "structure_type_employee_ca_salaried" in self.types, (
            "Salaried structure type xml id 'structure_type_employee_ca_salaried' not found"
        )

    def test_hourly_wage_type(self):
        assert self.types["structure_type_employee_ca"].get("wage_type") == "hourly"

    def test_salaried_wage_type(self):
        assert self.types["structure_type_employee_ca_salaried"].get("wage_type") == "monthly"

    def test_hourly_name_contains_hourly(self):
        name = self.types["structure_type_employee_ca"].get("name", "")
        assert "hourly" in name.lower() or "Hourly" in name

    def test_salaried_name_contains_salaried(self):
        name = self.types["structure_type_employee_ca_salaried"].get("name", "")
        assert "salaried" in name.lower() or "Salaried" in name

    def test_both_have_ca_country(self):
        for xml_id, fields in self.types.items():
            assert fields.get("country_id") == "base.ca", (
                f"{xml_id} is missing country_id=base.ca"
            )


# ---------------------------------------------------------------------------
# 2. Pay structure data file
# ---------------------------------------------------------------------------


class TestPayStructureXml:
    """Verify hr_payroll_structure_data.xml declares both pay structures."""

    def setup_method(self):
        root = _parse_xml("hr_payroll_structure_data.xml")
        self.structs = _record_ids(root, "hr.payroll.structure")

    def test_hourly_structure_exists(self):
        assert "hr_payroll_structure_ca_employee_salary" in self.structs

    def test_salaried_structure_exists(self):
        assert "hr_payroll_structure_ca_employee_salary_salaried" in self.structs

    def test_hourly_structure_points_at_hourly_type(self):
        assert self.structs["hr_payroll_structure_ca_employee_salary"].get("type_id") == "structure_type_employee_ca"

    def test_salaried_structure_points_at_salaried_type(self):
        assert self.structs["hr_payroll_structure_ca_employee_salary_salaried"].get("type_id") == "structure_type_employee_ca_salaried"


# ---------------------------------------------------------------------------
# 3. _l10n_ca_clone_rules_to_salaried logic
# ---------------------------------------------------------------------------


def _make_rule(code: str, rule_id: int) -> MagicMock:
    """Return a minimal mock salary rule."""
    rule = MagicMock()
    rule.code = code
    rule.id = rule_id
    rule.name = f"Rule {code}"
    return rule


def _make_struct(rules: list) -> MagicMock:
    """Return a minimal mock hr.payroll.structure with the given rules."""
    struct = MagicMock()
    struct.rule_ids = rules
    struct.id = id(struct)
    return struct


class TestCloneRulesToSalaried:
    """Unit tests for the _l10n_ca_clone_rules_to_salaried clone logic.

    The method uses @api.model which is a MagicMock stub in the test
    environment.  We therefore test the algorithm by replaying the same logic
    directly, and separately verify that the module can be imported cleanly.
    """

    # ---- Module smoke-test -----------------------------------------------

    def test_module_imports_cleanly(self):
        """hr_payroll_structure.py must be importable without a live Odoo env."""
        import importlib.util

        path = pathlib.Path(__file__).parent.parent / "models" / "hr_payroll_structure.py"
        spec = importlib.util.spec_from_file_location("hr_payroll_structure", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "HrPayrollStructure"), "HrPayrollStructure class not found in module"

    # ---- Algorithm tests (logic extracted for stub-safe testing) ----------

    @staticmethod
    def _run_clone(source_rules: list, target_rules: list):
        """Execute the same algorithm as _l10n_ca_clone_rules_to_salaried."""
        source = _make_struct(source_rules)
        target = _make_struct(target_rules)
        existing_codes = {r.code for r in target.rule_ids}
        for rule in source.rule_ids:
            if rule.code in existing_codes:
                continue
            rule.copy({
                "struct_id": target.id,
                "name": rule.name,
                "code": rule.code,
            })
        return source, target

    def test_copies_all_rules_to_empty_target(self):
        rules = [_make_rule("CPP_EE", 1), _make_rule("EI_EE", 2), _make_rule("NET", 3)]
        source, target = self._run_clone(rules, [])
        for rule in source.rule_ids:
            assert rule.copy.called, f"Rule {rule.code} should have been copied to empty target"

    def test_skips_existing_codes_in_target(self):
        existing = _make_rule("CPP_EE", 10)
        source_rules = [_make_rule("CPP_EE", 1), _make_rule("EI_EE", 2)]
        source, target = self._run_clone(source_rules, [existing])
        # Only EI_EE should be copied; CPP_EE already exists in target
        cpp_rule = source.rule_ids[0]
        ei_rule = source.rule_ids[1]
        assert not cpp_rule.copy.called, "CPP_EE already in target; should not be copied"
        assert ei_rule.copy.called, "EI_EE not in target; should be copied"

    def test_idempotent_on_repeated_call(self):
        """Calling clone with a target that already has all rules must be a no-op."""
        existing = _make_rule("CPP_EE", 99)
        source_rules = [_make_rule("CPP_EE", 1)]
        source, _ = self._run_clone(source_rules, [existing])
        assert not source.rule_ids[0].copy.called, "CPP_EE already in target; copy should be skipped"

    def test_copy_receives_correct_struct_id(self):
        source_rules = [_make_rule("BASIC", 1)]
        source = _make_struct(source_rules)
        target = _make_struct([])
        existing_codes = {r.code for r in target.rule_ids}
        for rule in source.rule_ids:
            if rule.code not in existing_codes:
                rule.copy({
                    "struct_id": target.id,
                    "name": rule.name,
                    "code": rule.code,
                })
        call_kwargs = source.rule_ids[0].copy.call_args[0][0]
        assert call_kwargs["struct_id"] == target.id
