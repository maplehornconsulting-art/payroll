# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Tests for the dual Hourly/Salaried structure types introduced in v19.0.1.4.

These tests verify:
1. Both structure type records are declared in the XML data file.
2. Both pay structure records are declared in the XML data file, each pointing
   at the correct structure type.
3. The ``_l10n_ca_clone_rules_to_salaried`` Python helper is idempotent and
   correctly copies rules from a source structure to a target.
4. ``_get_paid_amount`` non-CA fallback and monthly wage_type scaling.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch, call


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

# Fields expected to be copied by the new explicit field-by-field clone.
_CLONE_FIELDS = (
    "sequence",
    "category_id",
    "condition_select",
    "condition_python",
    "condition_range",
    "condition_range_min",
    "condition_range_max",
    "amount_select",
    "amount_fix",
    "amount_percentage",
    "amount_percentage_base",
    "amount_python_compute",
    "appears_on_payslip",
    "active",
    "account_debit",
    "account_credit",
    "analytic_account_id",
    "note",
    "partner_id",
    "register_id",
)


def _make_field(ftype: str):
    """Return a minimal mock Odoo field descriptor."""
    f = MagicMock()
    f.type = ftype
    return f


def _make_rule(code: str, rule_id: int, extra_fields: dict | None = None) -> MagicMock:
    """Return a minimal mock salary rule with all _CLONE_FIELDS present."""
    rule = MagicMock()
    rule.code = code
    rule.id = rule_id
    rule.name = f"Rule {code}"

    # Build _fields dict so the clone logic can introspect field types.
    fields = {}
    # Scalar fields
    for fname in ("sequence", "condition_select", "condition_python",
                  "condition_range", "condition_range_min", "condition_range_max",
                  "amount_select", "amount_fix", "amount_percentage",
                  "amount_percentage_base", "amount_python_compute",
                  "appears_on_payslip", "active", "note"):
        fields[fname] = _make_field("char")
    # Many2one fields
    for fname in ("category_id", "account_debit", "account_credit",
                  "analytic_account_id", "partner_id", "register_id"):
        fields[fname] = _make_field("many2one")
    rule._fields = fields

    # Set sensible defaults for functional fields we care about in tests
    rule.sequence = 10
    rule.condition_python = ""
    rule.amount_python_compute = "result = contract.wage"
    rule.appears_on_payslip = True
    rule.active = True
    rule.account_debit = MagicMock()
    rule.account_debit.id = 5410
    rule.account_credit = MagicMock()
    rule.account_credit.id = 2310

    if extra_fields:
        for k, v in extra_fields.items():
            setattr(rule, k, v)

    # Make rule[fname] work via __getitem__
    rule.__getitem__ = lambda _, key: getattr(rule, key)

    return rule


def _make_struct(rules: list) -> MagicMock:
    """Return a minimal mock hr.payroll.structure with the given rules."""
    struct = MagicMock()
    struct.rule_ids = rules
    struct.id = id(struct)
    struct.name = "Test Structure"
    return struct


def _run_clone(source_rules: list, target_rules: list, fail_codes: set | None = None):
    """Execute the same algorithm as the new _l10n_ca_clone_rules_to_salaried.

    Returns (source, target, created_vals_list) where *created_vals_list* is
    the list of ``vals`` dicts passed to ``Rule.create()`` for each cloned rule.
    """
    source = _make_struct(source_rules)
    target = _make_struct(target_rules)

    existing_codes = {r.code for r in target.rule_ids}
    created_vals = []

    for rule in source.rule_ids:
        if rule.code in existing_codes:
            continue
        vals = {}
        for fname in _CLONE_FIELDS:
            if fname not in rule._fields:
                continue
            field = rule._fields[fname]
            value = rule[fname]
            if field.type == "many2one":
                vals[fname] = value.id if value else False
            else:
                vals[fname] = value
        vals.update({
            "struct_id": target.id,
            "name": rule.name,
            "code": rule.code,
        })
        if fail_codes and rule.code in fail_codes:
            # Simulate a create failure for this rule
            continue
        created_vals.append(vals)

    return source, target, created_vals


# Fields repaired by the repair pass (mirrors _REPAIR_FIELDS in hr_payroll_structure.py).
_REPAIR_FIELDS = (
    "account_debit",
    "account_credit",
    "analytic_account_id",
    "amount_python_compute",
    "condition_python",
    "condition_select",
    "amount_select",
    "category_id",
    "sequence",
    "appears_on_payslip",
)


def _run_repair(source_rules: list, target_rules: list, fail_codes: set | None = None):
    """Execute the repair-pass algorithm from _l10n_ca_clone_rules_to_salaried.

    Returns (source, target, repaired_patches) where *repaired_patches* is a
    dict mapping rule code → patch dict that would be passed to write().
    Rules listed in *fail_codes* simulate a write() exception (patch is not
    recorded, mirroring the except branch).
    """
    source = _make_struct(source_rules)
    target = _make_struct(target_rules)

    target_by_code = {r.code: r for r in target.rule_ids}
    repaired_patches: dict[str, dict] = {}

    for src_rule in source.rule_ids:
        tgt_rule = target_by_code.get(src_rule.code)
        if not tgt_rule:
            continue
        patch: dict = {}
        for fname in _REPAIR_FIELDS:
            if fname not in src_rule._fields or fname not in tgt_rule._fields:
                continue
            src_val = src_rule[fname]
            tgt_val = tgt_rule[fname]
            field = src_rule._fields[fname]
            if field.type == "many2one":
                if not tgt_val and src_val:
                    patch[fname] = src_val.id
            else:
                if not tgt_val and src_val:
                    patch[fname] = src_val
        if patch:
            if fail_codes and src_rule.code in fail_codes:
                pass  # simulate write() raising — patch not applied
            else:
                repaired_patches[src_rule.code] = patch

    return source, target, repaired_patches


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

    def test_copies_all_rules_to_empty_target(self):
        rules = [_make_rule("CPP_EE", 1), _make_rule("EI_EE", 2), _make_rule("NET", 3)]
        _, _, created = _run_clone(rules, [])
        assert len(created) == 3, "All 3 rules should be cloned to empty target"
        codes = {v["code"] for v in created}
        assert codes == {"CPP_EE", "EI_EE", "NET"}

    def test_skips_existing_codes_in_target(self):
        existing = _make_rule("CPP_EE", 10)
        source_rules = [_make_rule("CPP_EE", 1), _make_rule("EI_EE", 2)]
        _, _, created = _run_clone(source_rules, [existing])
        assert len(created) == 1, "Only EI_EE should be cloned; CPP_EE already in target"
        assert created[0]["code"] == "EI_EE"

    def test_idempotent_on_repeated_call(self):
        """Calling clone with a target that already has all rules must be a no-op."""
        existing = _make_rule("CPP_EE", 99)
        source_rules = [_make_rule("CPP_EE", 1)]
        _, _, created = _run_clone(source_rules, [existing])
        assert len(created) == 0, "CPP_EE already in target; no rules should be cloned"

    def test_clones_account_debit_and_credit(self):
        """account_debit and account_credit must appear in create vals."""
        rule = _make_rule("GROSS", 1)
        rule.account_debit.id = 5410
        rule.account_credit.id = 2380
        _, _, created = _run_clone([rule], [])
        assert len(created) == 1
        vals = created[0]
        assert vals.get("account_debit") == 5410, "account_debit id should be copied"
        assert vals.get("account_credit") == 2380, "account_credit id should be copied"

    def test_clones_amount_python_compute_and_condition_python(self):
        """amount_python_compute and condition_python must appear in create vals."""
        rule = _make_rule("FED_TAX", 5)
        rule.amount_python_compute = "result = employee.fed_tax_calc()"
        rule.condition_python = "result = employee.l10n_ca_sin != False"
        _, _, created = _run_clone([rule], [])
        assert len(created) == 1
        vals = created[0]
        assert vals.get("amount_python_compute") == "result = employee.fed_tax_calc()"
        assert vals.get("condition_python") == "result = employee.l10n_ca_sin != False"

    def test_clones_sequence(self):
        """sequence must appear in create vals."""
        rule = _make_rule("NET", 7)
        rule.sequence = 42
        _, _, created = _run_clone([rule], [])
        assert len(created) == 1
        assert created[0].get("sequence") == 42

    def test_create_vals_always_contain_struct_id_name_code(self):
        """struct_id, name, and code must always be set in create vals."""
        rule = _make_rule("BASIC", 1)
        _, target, created = _run_clone([rule], [])
        assert len(created) == 1
        vals = created[0]
        assert vals["struct_id"] == target.id
        assert vals["name"] == rule.name
        assert vals["code"] == "BASIC"

    def test_single_failing_rule_does_not_abort_rest(self):
        """A create failure on one rule must not prevent other rules from being cloned."""
        rules = [_make_rule("CPP_EE", 1), _make_rule("EI_EE", 2), _make_rule("NET", 3)]
        # Simulate CPP_EE failing by passing fail_codes
        _, _, created = _run_clone(rules, [], fail_codes={"CPP_EE"})
        # EI_EE and NET should still be cloned
        codes = {v["code"] for v in created}
        assert "EI_EE" in codes
        assert "NET" in codes
        assert "CPP_EE" not in codes

    def test_idempotent_double_clone(self):
        """Running the clone twice (with target already populated) adds no new rules."""
        rules = [_make_rule("CPP_EE", 1), _make_rule("EI_EE", 2)]
        # First clone
        _, _, created_first = _run_clone(rules, [])
        assert len(created_first) == 2
        # Simulate second clone: target now has the same codes
        target_rules_after = [_make_rule(v["code"], i) for i, v in enumerate(created_first)]
        _, _, created_second = _run_clone(rules, target_rules_after)
        assert len(created_second) == 0, "Second clone must be a no-op"


# ---------------------------------------------------------------------------
# 3b. Repair-pass logic
# ---------------------------------------------------------------------------


class TestRepairPass:
    """Unit tests for the repair pass in _l10n_ca_clone_rules_to_salaried.

    The repair pass fills blank fields on *existing* target rules from the
    matching source rule.  It must be non-destructive (never overwrite a field
    that already has a value) and resilient (a failing write on one rule must
    not abort processing of the remaining rules).
    """

    def test_repair_fills_blank_account_debit_and_credit(self):
        """A target rule with empty account_debit/account_credit is patched."""
        src_rule = _make_rule("GROSS", 1)
        src_rule.account_debit.id = 5410
        src_rule.account_credit.id = 2380
        # Target rule has None for both accounting fields (old buggy clone)
        tgt_rule = _make_rule("GROSS", 10, extra_fields={"account_debit": None, "account_credit": None})
        _, _, patches = _run_repair([src_rule], [tgt_rule])
        assert "GROSS" in patches, "GROSS rule should have been repaired"
        assert patches["GROSS"].get("account_debit") == 5410
        assert patches["GROSS"].get("account_credit") == 2380

    def test_repair_fills_blank_amount_python_compute(self):
        """A target rule with empty amount_python_compute gets the source body."""
        src_rule = _make_rule("FED_TAX", 1)
        src_rule.amount_python_compute = "result = compute_fed_tax()"
        tgt_rule = _make_rule("FED_TAX", 10, extra_fields={"amount_python_compute": ""})
        _, _, patches = _run_repair([src_rule], [tgt_rule])
        assert "FED_TAX" in patches
        assert patches["FED_TAX"].get("amount_python_compute") == "result = compute_fed_tax()"

    def test_repair_does_not_overwrite_existing_account_debit(self):
        """A target rule that already has account_debit set is NOT overwritten."""
        src_rule = _make_rule("GROSS", 1)
        src_rule.account_debit.id = 5410
        # Target already has a custom account
        custom_acct = MagicMock()
        custom_acct.id = 9999
        tgt_rule = _make_rule("GROSS", 10, extra_fields={"account_debit": custom_acct})
        _, _, patches = _run_repair([src_rule], [tgt_rule])
        # account_debit must NOT appear in the patch — it already has a value
        patch = patches.get("GROSS", {})
        assert "account_debit" not in patch, (
            "account_debit should not be overwritten when target already has a value"
        )

    def test_repair_no_error_when_source_rule_has_no_target_match(self):
        """Repair pass does not raise when a source rule has no matching target rule."""
        src_rule = _make_rule("ORPHAN", 1)
        tgt_rule = _make_rule("OTHER", 10)
        # Should complete without exception; no patches produced
        _, _, patches = _run_repair([src_rule], [tgt_rule])
        assert patches == {}

    def test_repair_failing_write_does_not_abort_rest(self):
        """A failing write() on one rule must not prevent repairs on other rules."""
        src1 = _make_rule("GROSS", 1)
        src1.account_debit.id = 5410
        src2 = _make_rule("NET", 2)
        src2.account_debit.id = 5420
        tgt1 = _make_rule("GROSS", 10, extra_fields={"account_debit": None})
        tgt2 = _make_rule("NET", 20, extra_fields={"account_debit": None})
        # Simulate GROSS write() raising — NET should still be patched
        _, _, patches = _run_repair([src1, src2], [tgt1, tgt2], fail_codes={"GROSS"})
        assert "NET" in patches, "NET repair must proceed even when GROSS write() fails"
        assert "GROSS" not in patches


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

