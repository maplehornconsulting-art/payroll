# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Tests for the accounting integration added in v19.0.1.7.

All tests run without a live Odoo instance.  They fall into three categories:

1. **XML structure tests** — parse data XML files and assert that required
   records (accounts, journal, salary-rule account mappings) are present.

2. **Post-init hook tests** — exercise ``_ensure_payroll_accounts``,
   ``_ensure_sal_journal``, and ``_assign_journal_to_structures`` using
   lightweight mock objects.

3. **Idempotency tests** — verify that running the hook twice on the same
   environment does not create duplicate records.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_MODULE_DIR = pathlib.Path(__file__).parent.parent
_DATA_DIR = _MODULE_DIR / "data"


def _parse_xml(filename: str) -> ET.Element:
    return ET.parse(_DATA_DIR / filename).getroot()


def _record_ids(root: ET.Element, model: str) -> dict[str, dict[str, str]]:
    """Return {xml_id: {field_name: field_value/ref}} for <record> elements."""
    result: dict[str, dict[str, str]] = {}
    for rec in root.findall(f".//record[@model='{model}']"):
        rid = rec.get("id", "")
        fields: dict[str, str] = {}
        for fld in rec.findall("field"):
            name = fld.get("name", "")
            value = fld.get("ref") or fld.text or ""
            fields[name] = value.strip()
        result[rid] = fields
    return result


# ---------------------------------------------------------------------------
# Import the accounting constants and helpers from the standalone setup module
# (importable without Odoo or the full package context)
# ---------------------------------------------------------------------------

def _load_account_setup():
    """Import _account_setup.py helpers directly via importlib."""
    import importlib.util
    path = _MODULE_DIR / "_account_setup.py"
    spec = importlib.util.spec_from_file_location("l10n_ca_account_setup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_setup = _load_account_setup()
_PAYROLL_ACCOUNTS = _setup.PAYROLL_ACCOUNTS
_SAL_JOURNAL = _setup.SAL_JOURNAL
_ensure_payroll_accounts = _setup.ensure_payroll_accounts
_ensure_sal_journal = _setup.ensure_sal_journal
_assign_journal_to_structures = _setup.assign_journal_to_structures


# ===========================================================================
# 1. XML structure tests
# ===========================================================================


class TestAccountAccountDataXml:
    """Verify account_account_data.xml declares all 17 required GL accounts."""

    EXPECTED_LIABILITY_CODES = {'2310', '2320', '2321', '2330', '2340', '2350', '2360', '2370', '2380'}
    EXPECTED_EXPENSE_CODES = {'5410', '5411', '5412', '5413', '5420', '5421', '5430', '5440'}

    def setup_method(self):
        root = _parse_xml("account_account_data.xml")
        self.accounts = _record_ids(root, "account.account")
        self.codes_by_id = {rid: flds.get("code", "") for rid, flds in self.accounts.items()}
        self.all_codes = set(self.codes_by_id.values())

    def test_file_has_noupdate(self):
        root = _parse_xml("account_account_data.xml")
        assert root.get("noupdate") == "1", (
            "account_account_data.xml must use noupdate='1' to protect "
            "administrator customisations on upgrade"
        )

    def test_total_account_count(self):
        assert len(self.accounts) == 17, (
            f"Expected 17 account records, found {len(self.accounts)}: {list(self.accounts)}"
        )

    def test_all_liability_codes_present(self):
        missing = self.EXPECTED_LIABILITY_CODES - self.all_codes
        assert not missing, f"Missing liability account codes: {missing}"

    def test_all_expense_codes_present(self):
        missing = self.EXPECTED_EXPENSE_CODES - self.all_codes
        assert not missing, f"Missing expense account codes: {missing}"

    def test_liability_accounts_have_correct_type(self):
        for rid, flds in self.accounts.items():
            code = flds.get("code", "")
            if code in self.EXPECTED_LIABILITY_CODES:
                assert flds.get("account_type") == "liability_current", (
                    f"Account {code} ({rid}) should have account_type=liability_current"
                )

    def test_expense_accounts_have_correct_type(self):
        for rid, flds in self.accounts.items():
            code = flds.get("code", "")
            if code in self.EXPECTED_EXPENSE_CODES:
                assert flds.get("account_type") == "expense", (
                    f"Account {code} ({rid}) should have account_type=expense"
                )

    def test_net_pay_clearing_account_exists(self):
        assert '2380' in self.all_codes, "Net Pay Clearing (2380) must be declared"

    def test_fed_tax_payable_account_exists(self):
        assert '2310' in self.all_codes, "Federal Tax Payable (2310) must be declared"

    def test_cpp_payable_account_exists(self):
        assert '2320' in self.all_codes, "CPP Payable (2320) must be declared"

    def test_ei_payable_account_exists(self):
        assert '2330' in self.all_codes, "EI Payable (2330) must be declared"

    def test_prov_tax_payable_account_exists(self):
        assert '2340' in self.all_codes, "Provincial Tax Payable (2340) must be declared"

    def test_salaries_expense_account_exists(self):
        assert '5410' in self.all_codes, "Salaries & Wages Expense (5410) must be declared"

    def test_cpp_er_expense_account_exists(self):
        assert '5420' in self.all_codes, "CPP ER Expense (5420) must be declared"

    def test_ei_er_expense_account_exists(self):
        assert '5430' in self.all_codes, "EI ER Expense (5430) must be declared"

    def test_eht_accounts_exist(self):
        """EHT accounts are created now for future employer rule wiring."""
        assert '2350' in self.all_codes, "Ontario EHT Payable (2350) must be declared"
        assert '5440' in self.all_codes, "Ontario EHT Expense (5440) must be declared"

    def test_account_xml_ids_use_code_suffix(self):
        """XML IDs must follow the account_XXXX convention."""
        for rid in self.accounts:
            assert rid.startswith("account_"), (
                f"Account XML ID '{rid}' should start with 'account_'"
            )


class TestAccountJournalDataXml:
    """Verify account_journal_data.xml declares the SAL Salary Journal."""

    def setup_method(self):
        root = _parse_xml("account_journal_data.xml")
        self.journals = _record_ids(root, "account.journal")

    def test_file_has_noupdate(self):
        root = _parse_xml("account_journal_data.xml")
        assert root.get("noupdate") == "1", (
            "account_journal_data.xml must use noupdate='1'"
        )

    def test_sal_journal_exists(self):
        assert "account_journal_sal" in self.journals, (
            "SAL journal XML ID 'account_journal_sal' not found"
        )

    def test_sal_journal_code(self):
        assert self.journals["account_journal_sal"].get("code") == "SAL"

    def test_sal_journal_name(self):
        assert self.journals["account_journal_sal"].get("name") == "Salary Journal"

    def test_sal_journal_type_is_general(self):
        assert self.journals["account_journal_sal"].get("type") == "general", (
            "Salary Journal must have type='general' for payslip journal entries"
        )


class TestSalaryRuleAccountMappings:
    """Verify that salary rules have the correct account_debit/credit refs."""

    # Expected mappings: rule XML ID → (debit_account_ref, credit_account_ref)
    # None means the field should NOT be set (informational rule).
    #
    # NOTE on employee deduction rules (negative result):
    # Odoo's hr_payroll_account swaps account_debit ↔ account_credit when
    # salary_line.total < 0.  For deduction rules (result = -amount), the
    # LIABILITY account is therefore stored in account_debit and the clearing
    # account (2380) in account_credit.  The <!-- Dr / Cr --> comment above
    # each XML rule describes the *resulting* journal entry direction (after
    # the sign-based swap), not the literal field assignment.
    EXPECTED_MAPPINGS: dict[str, tuple[str | None, str | None]] = {
        'salary_rule_ca_gross':    ('account_5410', 'account_2380'),
        'salary_rule_ca_rrsp':     ('account_2360', 'account_2380'),
        'salary_rule_ca_union':    ('account_2370', 'account_2380'),
        'salary_rule_ca_cpp_ee':   ('account_2320', 'account_2380'),
        'salary_rule_ca_cpp2_ee':  ('account_2321', 'account_2380'),
        'salary_rule_ca_ei_ee':    ('account_2330', 'account_2380'),
        'salary_rule_ca_fed_tax':  ('account_2310', 'account_2380'),
        'salary_rule_ca_prov_tax': ('account_2340', 'account_2380'),
        'salary_rule_ca_ohp':      ('account_2340', 'account_2380'),
        'salary_rule_ca_cpp_er':   ('account_5420', 'account_2320'),
        'salary_rule_ca_cpp2_er':  ('account_5421', 'account_2321'),
        'salary_rule_ca_ei_er':    ('account_5430', 'account_2330'),
    }

    # Rules that are informational and must NOT have account fields set
    INFORMATIONAL_RULES = {
        'salary_rule_ca_basic',
        'salary_rule_ca_net',
    }

    def setup_method(self):
        root = _parse_xml("hr_salary_rule_data.xml")
        self.rules = _record_ids(root, "hr.salary.rule")

    def test_all_mapped_rules_have_account_debit(self):
        for rule_id, (expected_debit, _expected_credit) in self.EXPECTED_MAPPINGS.items():
            rule_fields = self.rules.get(rule_id, {})
            actual_debit = rule_fields.get("account_debit")
            assert actual_debit == expected_debit, (
                f"Rule {rule_id}: expected account_debit='{expected_debit}', "
                f"got '{actual_debit}'"
            )

    def test_all_mapped_rules_have_account_credit(self):
        for rule_id, (_expected_debit, expected_credit) in self.EXPECTED_MAPPINGS.items():
            rule_fields = self.rules.get(rule_id, {})
            actual_credit = rule_fields.get("account_credit")
            assert actual_credit == expected_credit, (
                f"Rule {rule_id}: expected account_credit='{expected_credit}', "
                f"got '{actual_credit}'"
            )

    def test_informational_rules_have_no_account_debit(self):
        for rule_id in self.INFORMATIONAL_RULES:
            rule_fields = self.rules.get(rule_id, {})
            assert "account_debit" not in rule_fields, (
                f"Informational rule {rule_id} should not have account_debit set"
            )

    def test_informational_rules_have_no_account_credit(self):
        for rule_id in self.INFORMATIONAL_RULES:
            rule_fields = self.rules.get(rule_id, {})
            assert "account_credit" not in rule_fields, (
                f"Informational rule {rule_id} should not have account_credit set"
            )

    def test_gross_debits_salaries_expense(self):
        assert self.rules.get('salary_rule_ca_gross', {}).get('account_debit') == 'account_5410'

    def test_gross_credits_net_pay_clearing(self):
        assert self.rules.get('salary_rule_ca_gross', {}).get('account_credit') == 'account_2380'

    def test_fed_tax_liability_in_debit_field(self):
        # For deduction rules (result < 0), Odoo swaps debit/credit at posting time.
        # The liability account therefore lives in account_debit; 2380 in account_credit.
        assert self.rules.get('salary_rule_ca_fed_tax', {}).get('account_debit') == 'account_2310'

    def test_cpp_ee_liability_in_debit_field(self):
        assert self.rules.get('salary_rule_ca_cpp_ee', {}).get('account_debit') == 'account_2320'

    def test_ei_ee_liability_in_debit_field(self):
        assert self.rules.get('salary_rule_ca_ei_ee', {}).get('account_debit') == 'account_2330'

    def test_prov_tax_liability_in_debit_field(self):
        assert self.rules.get('salary_rule_ca_prov_tax', {}).get('account_debit') == 'account_2340'

    def test_ohp_liability_in_debit_field(self):
        """OHP is remitted alongside provincial tax (both map to 2340)."""
        assert self.rules.get('salary_rule_ca_ohp', {}).get('account_debit') == 'account_2340'

    def test_cpp_er_debits_cpp_er_expense(self):
        assert self.rules.get('salary_rule_ca_cpp_er', {}).get('account_debit') == 'account_5420'

    def test_ei_er_debits_ei_er_expense(self):
        assert self.rules.get('salary_rule_ca_ei_er', {}).get('account_debit') == 'account_5430'

    def test_ohp_not_eht_payable(self):
        """OHP (employee deduction) maps to 2340, not 2350 (employer EHT)."""
        ohp = self.rules.get('salary_rule_ca_ohp', {})
        assert ohp.get('account_debit') != 'account_2350', (
            "OHP should use 2340 (provincial tax), not 2350 (employer EHT)"
        )


# ===========================================================================
# 2. Post-init hook unit tests
# ===========================================================================


def _make_company(company_id: int = 1, country_code: str = 'CA') -> MagicMock:
    """Return a minimal company mock."""
    company = MagicMock()
    company.id = company_id
    company.country_id.code = country_code
    return company


def _make_env(existing_account_codes: list[str] | None = None,
              existing_journal_codes: list[str] | None = None,
              company_id: int = 1) -> MagicMock:
    """Return a mock Odoo env with pre-populated accounts and journals."""
    existing_account_codes = existing_account_codes or []
    existing_journal_codes = existing_journal_codes or []

    # Build mock account records for pre-existing accounts
    mock_accounts = []
    for code in existing_account_codes:
        rec = MagicMock()
        rec.code = code
        mock_accounts.append(rec)

    # Build mock journal records for pre-existing journals
    mock_journals = []
    for code in existing_journal_codes:
        rec = MagicMock()
        rec.code = code
        mock_journals.append(rec)

    env = MagicMock()
    env.company.id = company_id

    # account.account.search returns mock_accounts
    def _account_search(domain, **kwargs):
        return mock_accounts

    account_model = MagicMock()
    account_model.search.side_effect = _account_search
    account_model.with_company.return_value = account_model
    account_model._fields = {'account_type': MagicMock()}
    account_model.create.return_value = MagicMock()

    # account.journal.search returns mock_journals
    def _journal_search(domain, limit=None):
        return mock_journals[:limit] if limit else mock_journals

    journal_model = MagicMock()
    journal_model.search.side_effect = _journal_search
    journal_model.with_company.return_value = journal_model
    journal_model.create.return_value = MagicMock()

    def _getitem(key):
        if key == 'account.account':
            return account_model
        if key == 'account.journal':
            return journal_model
        return MagicMock()

    # Use MagicMock(side_effect=...) so __getitem__ is called without 'self'
    env.__getitem__ = MagicMock(side_effect=_getitem)
    env.__contains__ = MagicMock(side_effect=lambda key: key in ('account.account', 'account.journal'))

    return env, account_model, journal_model


class TestEnsurePayrollAccounts:
    """Unit tests for _ensure_payroll_accounts."""

    def test_creates_all_accounts_when_none_exist(self):
        company = _make_company()
        env, account_model, _ = _make_env(existing_account_codes=[], company_id=company.id)

        _ensure_payroll_accounts(env, company)

        assert account_model.create.call_count == 17, (
            f"Expected 17 create calls, got {account_model.create.call_count}"
        )

    def test_skips_existing_accounts(self):
        company = _make_company()
        # Pre-populate all 17 accounts
        all_codes = [row[1] for row in _PAYROLL_ACCOUNTS]
        env, account_model, _ = _make_env(existing_account_codes=all_codes, company_id=company.id)

        _ensure_payroll_accounts(env, company)

        account_model.create.assert_not_called()

    def test_creates_only_missing_accounts(self):
        company = _make_company()
        # Already have 2310 and 5410 — 15 others must be created
        env, account_model, _ = _make_env(
            existing_account_codes=['2310', '5410'],
            company_id=company.id,
        )

        _ensure_payroll_accounts(env, company)

        assert account_model.create.call_count == 15

    def test_created_accounts_have_company_id(self):
        company = _make_company(company_id=42)
        env, account_model, _ = _make_env(existing_account_codes=[], company_id=42)

        _ensure_payroll_accounts(env, company)

        for c in account_model.create.call_args_list:
            vals = c[0][0]
            assert vals.get('company_id') == 42, (
                f"Account create called without company_id=42: {vals}"
            )

    def test_liability_accounts_have_reconcile_true(self):
        company = _make_company()
        env, account_model, _ = _make_env(existing_account_codes=[], company_id=company.id)

        _ensure_payroll_accounts(env, company)

        liability_codes = {'2310', '2320', '2321', '2330', '2340', '2350', '2360', '2370', '2380'}
        for c in account_model.create.call_args_list:
            vals = c[0][0]
            code = vals.get('code', '')
            if code in liability_codes:
                assert vals.get('reconcile') is True, (
                    f"Liability account {code} should have reconcile=True"
                )

    def test_expense_accounts_do_not_set_reconcile(self):
        company = _make_company()
        env, account_model, _ = _make_env(existing_account_codes=[], company_id=company.id)

        _ensure_payroll_accounts(env, company)

        expense_codes = {'5410', '5411', '5412', '5413', '5420', '5421', '5430', '5440'}
        for c in account_model.create.call_args_list:
            vals = c[0][0]
            code = vals.get('code', '')
            if code in expense_codes:
                assert 'reconcile' not in vals, (
                    f"Expense account {code} should not have reconcile set"
                )

    def test_all_17_account_definitions_in_constant(self):
        """_PAYROLL_ACCOUNTS must have exactly 17 entries."""
        assert len(_PAYROLL_ACCOUNTS) == 17


class TestEnsureSalJournal:
    """Unit tests for _ensure_sal_journal."""

    def test_creates_journal_when_absent(self):
        company = _make_company()
        env, _, journal_model = _make_env(existing_journal_codes=[], company_id=company.id)

        journal = _ensure_sal_journal(env, company)

        journal_model.create.assert_called_once()
        vals = journal_model.create.call_args[0][0]
        assert vals['code'] == 'SAL'
        assert vals['type'] == 'general'
        assert vals['name'] == 'Salary Journal'

    def test_returns_existing_journal_without_creating(self):
        company = _make_company()
        env, _, journal_model = _make_env(existing_journal_codes=['SAL'], company_id=company.id)

        _ensure_sal_journal(env, company)

        journal_model.create.assert_not_called()

    def test_journal_gets_company_id(self):
        company = _make_company(company_id=99)
        env, _, journal_model = _make_env(existing_journal_codes=[], company_id=99)

        _ensure_sal_journal(env, company)

        vals = journal_model.create.call_args[0][0]
        assert vals.get('company_id') == 99


class TestAssignJournalToStructures:
    """Unit tests for _assign_journal_to_structures."""

    def _make_env_with_structures(self, hourly_has_journal=False, salaried_has_journal=False):
        env = MagicMock()
        journal = MagicMock()

        hourly_struct = MagicMock()
        hourly_struct.journal_id = MagicMock() if hourly_has_journal else False

        salaried_struct = MagicMock()
        salaried_struct.journal_id = MagicMock() if salaried_has_journal else False

        def _ref(xmlid, raise_if_not_found=True):
            if 'salary_salaried' in xmlid:
                return salaried_struct
            return hourly_struct

        env.ref.side_effect = _ref

        Structure = MagicMock()
        Structure._fields = {'journal_id': MagicMock()}
        env.__getitem__ = lambda self, key: Structure if key == 'hr.payroll.structure' else MagicMock()

        return env, journal, hourly_struct, salaried_struct

    def test_sets_journal_on_structures_without_journal(self):
        env, journal, hourly, salaried = self._make_env_with_structures(False, False)

        _assign_journal_to_structures(env, journal)

        assert hourly.journal_id == journal
        assert salaried.journal_id == journal

    def test_does_not_overwrite_existing_journal(self):
        env, journal, hourly, salaried = self._make_env_with_structures(True, True)
        original_hourly_journal = hourly.journal_id
        original_salaried_journal = salaried.journal_id

        _assign_journal_to_structures(env, journal)

        # journal_id should NOT have been reassigned
        assert hourly.journal_id == original_hourly_journal
        assert salaried.journal_id == original_salaried_journal

    def test_skips_gracefully_when_journal_id_field_absent(self):
        """Graceful degradation when hr_payroll_account is not installed."""
        env = MagicMock()
        journal = MagicMock()

        Structure = MagicMock()
        Structure._fields = {}  # no journal_id field
        env.__getitem__ = lambda self, key: Structure

        # Should not raise
        _assign_journal_to_structures(env, journal)

        Structure.assert_not_called()


# ===========================================================================
# 3. Idempotency tests
# ===========================================================================


class TestIdempotency:
    """Verify that running the accounting setup helpers twice is a no-op."""

    def test_ensure_accounts_idempotent(self):
        """Second call with all accounts present must not create any."""
        company = _make_company()
        all_codes = [row[1] for row in _PAYROLL_ACCOUNTS]
        env, account_model, _ = _make_env(existing_account_codes=all_codes, company_id=company.id)

        _ensure_payroll_accounts(env, company)
        _ensure_payroll_accounts(env, company)

        account_model.create.assert_not_called()

    def test_ensure_journal_idempotent(self):
        """Second call with SAL journal present must not create it again."""
        company = _make_company()
        env, _, journal_model = _make_env(existing_journal_codes=['SAL'], company_id=company.id)

        _ensure_sal_journal(env, company)
        _ensure_sal_journal(env, company)

        journal_model.create.assert_not_called()


# ===========================================================================
# 4. OHP / EHT province tests (logic-level)
# ===========================================================================


class TestOhpAccountMapping:
    """Verify the OHP account mapping is correct for ON vs non-ON employees."""

    def test_ohp_uses_provincial_tax_payable_not_eht(self):
        """OHP (employee deduction) must credit 2340, not 2350 (employer EHT)."""
        root = _parse_xml("hr_salary_rule_data.xml")
        rules = _record_ids(root, "hr.salary.rule")
        ohp_credit = rules.get('salary_rule_ca_ohp', {}).get('account_credit', '')
        assert ohp_credit == 'account_2340', (
            f"OHP must credit 2340 (Provincial Tax Payable), got '{ohp_credit}'"
        )

    def test_ohp_debits_net_pay_clearing(self):
        root = _parse_xml("hr_salary_rule_data.xml")
        rules = _record_ids(root, "hr.salary.rule")
        ohp_debit = rules.get('salary_rule_ca_ohp', {}).get('account_debit', '')
        assert ohp_debit == 'account_2380', (
            f"OHP must debit 2380 (Net Pay Clearing), got '{ohp_debit}'"
        )

    def test_eht_accounts_created_for_future_employer_rule(self):
        """EHT accounts 5440/2350 exist even though no EHT rule is wired yet."""
        root = _parse_xml("account_account_data.xml")
        accounts = _record_ids(root, "account.account")
        all_codes = {flds.get('code') for flds in accounts.values()}
        assert '5440' in all_codes, "EHT Expense account 5440 not declared"
        assert '2350' in all_codes, "EHT Payable account 2350 not declared"


# ===========================================================================
# 5. Manifest dependency tests
# ===========================================================================


class TestManifestDependencies:
    """Verify __manifest__.py declares the required accounting dependencies."""

    def setup_method(self):
        import ast
        manifest_path = _MODULE_DIR / "__manifest__.py"
        tree = ast.parse(manifest_path.read_text())
        # The manifest is a module-level expression: Expr(value=Dict(...))
        expr = tree.body[0]
        assert isinstance(expr, ast.Expr), "Manifest must be a top-level expression"
        manifest_dict = ast.literal_eval(expr.value)
        self.manifest = manifest_dict

    def test_hr_payroll_account_in_depends(self):
        assert 'hr_payroll_account' in self.manifest.get('depends', []), (
            "hr_payroll_account must be in depends to enable GL posting"
        )

    def test_l10n_ca_in_depends(self):
        assert 'l10n_ca' in self.manifest.get('depends', []), (
            "l10n_ca must be in depends to provide the Canadian Chart of Accounts"
        )

    def test_version_bumped(self):
        version = self.manifest.get('version', '')
        assert version == '19.0.1.7', (
            f"Version should be 19.0.1.7, got '{version}'"
        )

    def test_account_account_data_in_data_list(self):
        data_files = self.manifest.get('data', [])
        assert 'data/account_account_data.xml' in data_files

    def test_account_journal_data_in_data_list(self):
        data_files = self.manifest.get('data', [])
        assert 'data/account_journal_data.xml' in data_files

    def test_account_data_loaded_before_salary_rules(self):
        """Accounts must be declared before salary rules reference them."""
        data_files = self.manifest.get('data', [])
        account_idx = data_files.index('data/account_account_data.xml')
        rule_idx = data_files.index('data/hr_salary_rule_data.xml')
        assert account_idx < rule_idx, (
            "account_account_data.xml must appear before hr_salary_rule_data.xml"
        )

    def test_journal_data_loaded_before_salary_rules(self):
        data_files = self.manifest.get('data', [])
        journal_idx = data_files.index('data/account_journal_data.xml')
        rule_idx = data_files.index('data/hr_salary_rule_data.xml')
        assert journal_idx < rule_idx, (
            "account_journal_data.xml must appear before hr_salary_rule_data.xml"
        )
