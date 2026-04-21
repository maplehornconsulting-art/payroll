# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Salaried-structure install parity tests.

Verifies (without a live Odoo instance) that the XML declarations for both
structures are complete and symmetric.  These tests are the static equivalent
of "install the module on a fresh DB and create a salaried payslip" — they
assert that every rule declared on the Hourly structure has a parallel
``_salaried`` record declared on the Salaried structure with:

- The same rule ``code``.
- A ``struct_id`` pointing at the Salaried structure.
- An ``amount_python_compute`` body that calls the identical helper method.
- A ``sequence`` and ``category_id`` matching the Hourly record.

These checks must pass on a fresh install with **no** ``-u`` step, because
rules are declared statically — not created at runtime by a clone function.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"

_HOURLY_STRUCT_REF = "hr_payroll_structure_ca_employee_salary"
_SALARIED_STRUCT_REF = "hr_payroll_structure_ca_employee_salary_salaried"


def _parse_salary_rules() -> tuple[dict, dict]:
    """Return (hourly_rules, salaried_rules) where each is {code: fields_dict}."""
    root = ET.parse(_DATA_DIR / "hr_salary_rule_data.xml").getroot()
    hourly: dict[str, dict] = {}
    salaried: dict[str, dict] = {}
    for rec in root.findall(".//record[@model='hr.salary.rule']"):
        xml_id = rec.get("id", "")
        fields: dict = {"_xml_id": xml_id}
        for fld in rec.findall("field"):
            name = fld.get("name", "")
            value = fld.get("ref") or fld.text or ""
            fields[name] = value.strip()
        code = fields.get("code", "")
        struct = fields.get("struct_id", "")
        if not code:
            continue
        if struct == _HOURLY_STRUCT_REF:
            hourly[code] = fields
        elif struct == _SALARIED_STRUCT_REF:
            salaried[code] = fields
    return hourly, salaried


class TestSalariedInstallParity:
    """Assert that a fresh install produces symmetric rule sets on both structures.

    No live Odoo instance required — all checks are against the XML data files
    that are loaded verbatim by Odoo's ORM during ``-i`` (install).
    """

    def setup_method(self):
        self.hourly, self.salaried = _parse_salary_rules()

    # ------------------------------------------------------------------
    # 1. Structure-level parity
    # ------------------------------------------------------------------

    def test_both_structures_have_rules_declared(self):
        assert self.hourly, "No rules found for the Hourly structure in hr_salary_rule_data.xml"
        assert self.salaried, "No rules found for the Salaried structure in hr_salary_rule_data.xml"

    def test_same_rule_codes_on_both_structures(self):
        only_hourly = set(self.hourly) - set(self.salaried)
        only_salaried = set(self.salaried) - set(self.hourly)
        assert not only_hourly, (
            f"Rules present on Hourly but missing from Salaried: {sorted(only_hourly)}\n"
            "Add a parallel '<record id=\"..._salaried\">' for each missing code."
        )
        assert not only_salaried, (
            f"Rules present on Salaried but missing from Hourly: {sorted(only_salaried)}"
        )

    # ------------------------------------------------------------------
    # 2. Per-rule field parity
    # ------------------------------------------------------------------

    def test_basic_rule_present_on_both_structures(self):
        assert 'BASIC' in self.hourly, "BASIC rule missing from Hourly structure"
        assert 'BASIC' in self.salaried, "BASIC rule missing from Salaried structure"

    def test_gross_rule_present_on_both_structures(self):
        assert 'GROSS' in self.hourly, "GROSS rule missing from Hourly structure"
        assert 'GROSS' in self.salaried, "GROSS rule missing from Salaried structure"

    def test_net_rule_present_on_both_structures(self):
        assert 'NET' in self.hourly, "NET rule missing from Hourly structure"
        assert 'NET' in self.salaried, "NET rule missing from Salaried structure"

    def test_deduction_rules_present_on_salaried(self):
        for code in ('CPP_EE', 'CPP2_EE', 'EI_EE', 'FED_TAX', 'PROV_TAX'):
            assert code in self.salaried, (
                f"{code} is missing from the Salaried structure XML — "
                "this rule must be declared statically for fresh-install correctness."
            )

    def test_employer_rules_present_on_salaried(self):
        for code in ('CPP_ER', 'CPP2_ER', 'EI_ER'):
            assert code in self.salaried, f"{code} missing from Salaried structure"

    def test_each_salaried_rule_calls_same_helper_as_hourly(self):
        """Every salaried rule must call the same _l10n_ca_compute_* helper as its hourly twin."""
        mismatches = []
        for code, hourly_fields in self.hourly.items():
            salaried_fields = self.salaried.get(code)
            if not salaried_fields:
                continue  # already caught by test_same_rule_codes_on_both_structures
            h_body = hourly_fields.get("amount_python_compute", "")
            s_body = salaried_fields.get("amount_python_compute", "")
            if h_body != s_body:
                mismatches.append((code, h_body[:60], s_body[:60]))
        assert not mismatches, (
            "Hourly and Salaried rules have different compute bodies:\n"
            + "\n".join(
                f"  {code}:\n    Hourly:   {h!r}\n    Salaried: {s!r}"
                for code, h, s in mismatches
            )
        )

    def test_each_salaried_rule_has_same_sequence_as_hourly(self):
        mismatches = []
        for code, hourly_fields in self.hourly.items():
            salaried_fields = self.salaried.get(code)
            if not salaried_fields:
                continue
            h_seq = hourly_fields.get("sequence", "")
            s_seq = salaried_fields.get("sequence", "")
            if h_seq != s_seq:
                mismatches.append((code, h_seq, s_seq))
        assert not mismatches, (
            "Sequence mismatch between Hourly and Salaried rules:\n"
            + "\n".join(f"  {code}: Hourly={h}, Salaried={s}" for code, h, s in mismatches)
        )

    def test_each_salaried_rule_has_same_category_as_hourly(self):
        mismatches = []
        for code, hourly_fields in self.hourly.items():
            salaried_fields = self.salaried.get(code)
            if not salaried_fields:
                continue
            h_cat = hourly_fields.get("category_id", "")
            s_cat = salaried_fields.get("category_id", "")
            if h_cat != s_cat:
                mismatches.append((code, h_cat, s_cat))
        assert not mismatches, (
            "Category mismatch between Hourly and Salaried rules:\n"
            + "\n".join(f"  {code}: Hourly={h}, Salaried={s}" for code, h, s in mismatches)
        )

    def test_salaried_xmlids_have_salaried_suffix(self):
        """Salaried rule xml ids must all end with '_salaried'."""
        bad = [
            f"{fields['_xml_id']} (code={code})"
            for code, fields in self.salaried.items()
            if not fields["_xml_id"].endswith("_salaried")
        ]
        assert not bad, (
            "Salaried rule records missing '_salaried' suffix in xml id:\n"
            + "\n".join(f"  {x}" for x in bad)
        )

    def test_no_function_tag_in_xml(self):
        """The runtime-clone <function> tag must not be present."""
        root = ET.parse(_DATA_DIR / "hr_salary_rule_data.xml").getroot()
        fn_tags = root.findall(".//function")
        assert not fn_tags, (
            "Found <function> tags in hr_salary_rule_data.xml — "
            "the runtime clone machinery must be removed entirely."
        )

    def test_compute_helpers_declared_on_hr_payslip(self):
        """Each _l10n_ca_compute_* helper referenced in XML must exist in hr_payslip.py."""
        import re
        payslip_path = pathlib.Path(__file__).parent.parent / "models" / "hr_payslip.py"
        source = payslip_path.read_text()
        # Find all helper names referenced in the XML
        root = ET.parse(_DATA_DIR / "hr_salary_rule_data.xml").getroot()
        referenced = set()
        for rec in root.findall(".//record[@model='hr.salary.rule']"):
            for fld in rec.findall("field[@name='amount_python_compute']"):
                body = fld.text or ""
                m = re.search(r'payslip\.(_l10n_ca_compute_\w+)', body)
                if m:
                    referenced.add(m.group(1))
        missing = [name for name in referenced if f"def {name}" not in source]
        assert not missing, (
            f"Helper methods referenced in XML but not found in hr_payslip.py: {missing}"
        )
