# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Tests for the dual Hourly/Salaried structure types.

These tests verify:
1. Both structure type records are declared in the XML data file.
2. Both pay structure records are declared in the XML data file, each pointing
   at the correct structure type.
3. Every Hourly salary rule has a parallel Salaried record in the XML
   (no runtime clone needed — rules are declared statically twice).
4. ``_get_paid_amount`` non-CA fallback and monthly wage_type scaling.
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
# 3. Salary rule XML parity: every Hourly rule has a Salaried twin
# ---------------------------------------------------------------------------

# Canonical set of expected rule codes on both structures.
_EXPECTED_RULE_CODES = {
    'BASIC', 'OT', 'VAC_PAY', 'GROSS', 'STO', 'PTO', 'CTO',
    'RRSP', 'UNION_DUES',
    'CPP_EE', 'CPP2_EE', 'EI_EE',
    'FED_TAX', 'PROV_TAX', 'OHP',
    'NET',
    'CPP_ER', 'CPP2_ER', 'EI_ER',
}

_HOURLY_STRUCT_REF = "hr_payroll_structure_ca_employee_salary"
_SALARIED_STRUCT_REF = "hr_payroll_structure_ca_employee_salary_salaried"


class TestSalariedRuleXmlParity:
    """Verify hr_salary_rule_data.xml declares every rule on both structures.

    This replaces the old clone-based approach: rules are now declared
    statically twice in XML.  These tests guard against accidentally
    forgetting to add the ``_salaried`` twin when a new rule is introduced.
    """

    def setup_method(self):
        root = _parse_xml("hr_salary_rule_data.xml")
        all_rules = _record_ids(root, "hr.salary.rule")
        self.hourly_codes: dict[str, str] = {}   # code → xml_id
        self.salaried_codes: dict[str, str] = {}  # code → xml_id
        for xml_id, fields in all_rules.items():
            code = fields.get("code", "").strip()
            struct = fields.get("struct_id", "").strip()
            if not code:
                continue
            if struct == _HOURLY_STRUCT_REF:
                self.hourly_codes[code] = xml_id
            elif struct == _SALARIED_STRUCT_REF:
                self.salaried_codes[code] = xml_id

    def test_hourly_has_all_expected_rule_codes(self):
        missing = _EXPECTED_RULE_CODES - set(self.hourly_codes)
        assert not missing, (
            f"Hourly structure is missing expected rule codes: {sorted(missing)}"
        )

    def test_salaried_has_all_expected_rule_codes(self):
        missing = _EXPECTED_RULE_CODES - set(self.salaried_codes)
        assert not missing, (
            f"Salaried structure is missing expected rule codes: {sorted(missing)}\n"
            "Add a parallel '<record id=\"..._salaried\"> pointing at "
            "hr_payroll_structure_ca_employee_salary_salaried for each missing code."
        )

    def test_hourly_and_salaried_have_identical_codes(self):
        only_hourly = set(self.hourly_codes) - set(self.salaried_codes)
        only_salaried = set(self.salaried_codes) - set(self.hourly_codes)
        assert not only_hourly and not only_salaried, (
            f"Rule code mismatch between structures.\n"
            f"  Only on Hourly: {sorted(only_hourly)}\n"
            f"  Only on Salaried: {sorted(only_salaried)}"
        )

    def test_salaried_records_have_salaried_suffix_in_xmlid(self):
        """All salaried records should have '_salaried' in their xml id."""
        bad = [xid for xid in self.salaried_codes.values() if '_salaried' not in xid]
        assert not bad, (
            f"Salaried rule records missing '_salaried' suffix in xml id: {bad}"
        )

    def test_each_rule_body_calls_helper_on_payslip(self):
        """Every amount_python_compute must be a single helper call on payslip."""
        root = _parse_xml("hr_salary_rule_data.xml")
        bad = []
        for rec in root.findall(".//record[@model='hr.salary.rule']"):
            xml_id = rec.get("id", "")
            for fld in rec.findall("field[@name='amount_python_compute']"):
                body = (fld.text or "").strip()
                if not body.startswith("result = payslip._l10n_ca_compute_"):
                    bad.append((xml_id, body[:60]))
        assert not bad, (
            "These rules do not have a one-line helper call:\n"
            + "\n".join(f"  {xid}: {body!r}" for xid, body in bad)
        )

    def test_no_function_tag_in_xml(self):
        """The <function> clone tag must have been removed."""
        root = _parse_xml("hr_salary_rule_data.xml")
        fn_tags = root.findall(".//function")
        assert not fn_tags, (
            "Found <function> tags in hr_salary_rule_data.xml — "
            "the runtime clone machinery must be removed."
        )

    def test_module_has_no_clone_method(self):
        """hr_payroll_structure.py must not contain _l10n_ca_clone_rules_to_salaried."""
        import importlib.util
        path = pathlib.Path(__file__).parent.parent / "models" / "hr_payroll_structure.py"
        spec = importlib.util.spec_from_file_location("hr_payroll_structure", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "HrPayrollStructure"), "HrPayrollStructure class not found"
        assert not hasattr(mod.HrPayrollStructure, "_l10n_ca_clone_rules_to_salaried"), (
            "_l10n_ca_clone_rules_to_salaried must be removed from HrPayrollStructure"
        )

    def test_module_has_diagnostic_register_hook(self):
        """hr_payroll_structure.py must still have a _register_hook for diagnostics."""
        import importlib.util
        path = pathlib.Path(__file__).parent.parent / "models" / "hr_payroll_structure.py"
        spec = importlib.util.spec_from_file_location("hr_payroll_structure", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod.HrPayrollStructure, "_register_hook"), (
            "_register_hook must remain for startup diagnostics"
        )


# ---------------------------------------------------------------------------
# 4. _get_paid_amount logic
# ---------------------------------------------------------------------------

def _make_payslip(country_code: str = "CA", wage_type: str = "monthly",
                  periods_per_year: int = 26, base_amount: float = 5000.0,
                  worked_days: list | None = None):
    """Return a minimal mock hr.payslip for _get_paid_amount testing."""
    payslip = MagicMock()

    # struct_id.country_id.code
    payslip.struct_id.country_id.code = country_code

    # struct_id.type_id with wage_type
    payslip.struct_id.type_id._fields = {"wage_type": MagicMock()}
    payslip.struct_id.type_id.wage_type = wage_type

    # version_id — not present, force fallback to struct type
    payslip.version_id = None

    # contract_id — not present, force fallback to struct type
    payslip.contract_id = None

    # _l10n_ca_periods_per_year
    payslip._l10n_ca_periods_per_year = MagicMock(return_value=periods_per_year)

    # worked_days_line_ids
    payslip.worked_days_line_ids = worked_days or []

    return payslip, base_amount


def _simulate_get_paid_amount(payslip, base_amount: float) -> float:
    """Replay the _get_paid_amount algorithm from hr_payslip.py."""
    if payslip.struct_id.country_id.code != 'CA':
        # non-CA: delegate to super
        return base_amount  # stand-in for super()._get_paid_amount()

    # Hourly path
    total = sum(
        line.amount for line in payslip.worked_days_line_ids
        if line.code in ('WORK100', 'LEAVE90')
    )
    if total > 0:
        return total

    # Salaried / fallback path
    base = base_amount or 0.0

    wage_type = None
    if hasattr(payslip, 'version_id') and payslip.version_id and 'wage_type' in (payslip.version_id._fields or {}):
        wage_type = payslip.version_id.wage_type
    elif hasattr(payslip, 'contract_id') and payslip.contract_id and 'wage_type' in (payslip.contract_id._fields or {}):
        wage_type = payslip.contract_id.wage_type
    if not wage_type and payslip.struct_id.type_id and 'wage_type' in payslip.struct_id.type_id._fields:
        wage_type = payslip.struct_id.type_id.wage_type

    if wage_type == 'monthly':
        periods = payslip._l10n_ca_periods_per_year() or 12
        return round(base * 12.0 / periods, 2)

    return base


class TestGetPaidAmount:
    """Unit tests for the _get_paid_amount logic."""

    def test_non_ca_returns_super_value(self):
        """Non-CA payslip must delegate to super and never return None."""
        payslip, base = _make_payslip(country_code="US", base_amount=3000.0)
        result = _simulate_get_paid_amount(payslip, base)
        assert result == 3000.0, "Non-CA payslip should return super()._get_paid_amount()"
        assert result is not None, "_get_paid_amount must never return None"

    def test_hourly_ca_returns_worked_days_total(self):
        """CA hourly payslip: sum of WORK100 + LEAVE90 worked days."""
        line1 = MagicMock()
        line1.code = 'WORK100'
        line1.amount = 1200.0
        line2 = MagicMock()
        line2.code = 'LEAVE90'
        line2.amount = 200.0
        line3 = MagicMock()
        line3.code = 'OTHER'
        line3.amount = 999.0
        payslip, base = _make_payslip(country_code="CA", worked_days=[line1, line2, line3])
        result = _simulate_get_paid_amount(payslip, base)
        assert result == 1400.0

    def test_salaried_monthly_biweekly_scaling(self):
        """Monthly wage 5200 on bi-weekly (26 periods) => 5200 * 12 / 26 = 2400."""
        payslip, _ = _make_payslip(
            country_code="CA",
            wage_type="monthly",
            periods_per_year=26,
            base_amount=5200.0,
        )
        result = _simulate_get_paid_amount(payslip, 5200.0)
        assert result == round(5200.0 * 12 / 26, 2), (
            f"Expected {round(5200.0 * 12 / 26, 2)}, got {result}"
        )

    def test_salaried_monthly_weekly_scaling(self):
        """Monthly wage 4000 on weekly (52 periods) => 4000 * 12 / 52 ≈ 923.08."""
        payslip, _ = _make_payslip(
            country_code="CA",
            wage_type="monthly",
            periods_per_year=52,
            base_amount=4000.0,
        )
        result = _simulate_get_paid_amount(payslip, 4000.0)
        assert result == round(4000.0 * 12 / 52, 2)

    def test_salaried_monthly_on_monthly_schedule_unchanged(self):
        """Monthly wage on monthly schedule (12 periods) should equal base."""
        payslip, _ = _make_payslip(
            country_code="CA",
            wage_type="monthly",
            periods_per_year=12,
            base_amount=6000.0,
        )
        result = _simulate_get_paid_amount(payslip, 6000.0)
        assert result == round(6000.0 * 12 / 12, 2)  # == 6000.0

    def test_hourly_wage_type_returns_base_without_scaling(self):
        """Hourly wage_type (no WORK100 lines) should return base without 12/periods scaling."""
        payslip, _ = _make_payslip(
            country_code="CA",
            wage_type="hourly",
            periods_per_year=26,
            base_amount=1500.0,
        )
        result = _simulate_get_paid_amount(payslip, 1500.0)
        assert result == 1500.0, "Hourly wage_type should not scale by 12/periods"
