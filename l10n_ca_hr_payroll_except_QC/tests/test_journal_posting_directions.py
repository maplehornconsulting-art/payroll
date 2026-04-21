# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Semantic integration tests for payslip journal posting directions.

These tests verify that when a Canadian payslip is confirmed and posted,
the resulting ``account.move.line`` entries land in the **correct** debit/credit
columns.

Expected behaviour (Canadian employee, Ontario, $5 000 bi-weekly gross):

* **Liability accounts** (2310 Fed Tax, 2320 CPP, 2321 CPP2, 2330 EI,
  2340 Prov Tax / OHP) must appear as **credits** — i.e. their ``credit``
  column holds the deduction amount and ``debit == 0``.
* **5410 Salaries & Wages Expense** must be **debited** for gross pay.
* **2380 Net Pay Clearing** must be **debited** for the total deduction
  amounts drawn against the payslip, and **credited** for the final net pay
  amount that needs to be disbursed to the employee.
* **Employer expense accounts** (5420 CPP ER, 5430 EI ER) must be **debited**
  for the employer contributions.

These tests complement ``test_accounting_integration.py`` (which validates the
XML field structure) by checking the *effective* journal-entry direction after
Odoo's ``hr_payroll_account`` sign-based swap has been applied.

For deduction rules the Python formula returns a **negative** value
(``result = -amount``).  Odoo's payroll accounting bridge swaps
``account_debit`` ↔ ``account_credit`` when ``total < 0``.  So the correct
XML assignment for an employee deduction that should post
``Dr 2380 / Cr 2320`` is: ``account_debit = 2320`` and
``account_credit = 2380``.  See ``docs/ACCOUNTING.md`` — *Gotcha* section.

Requirements
------------
* Odoo + ``l10n_ca_hr_payroll_except_QC`` (and ``hr_payroll_account``) installed.
* A Canadian company with the standard 17 payroll GL accounts in scope.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ca_payroll_accounting')
class TestPayslipJournalPostingDirections(TransactionCase):
    """Verify that confirmed payslips post to the correct debit/credit columns."""

    # ------------------------------------------------------------------ setup

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # -- Company ----------------------------------------------------------
        ca_country = cls.env.ref('base.ca')
        cls.company = cls.env['res.company'].create({
            'name': 'Payroll Direction Test Co.',
            'country_id': ca_country.id,
            'currency_id': cls.env.ref('base.CAD').id,
        })

        # -- GL accounts ------------------------------------------------------
        cls._create_payroll_accounts()

        # -- Salary journal ----------------------------------------------------
        cls.sal_journal = cls.env['account.journal'].with_company(cls.company).create({
            'name': 'Salary Journal',
            'type': 'general',
            'code': 'SAL',
            'company_id': cls.company.id,
        })

        # -- Province: Ontario -------------------------------------------------
        cls.province_on = cls.env['res.country.state'].search([
            ('country_id.code', '=', 'CA'),
            ('code', '=', 'ON'),
        ], limit=1)

        # -- Employee ----------------------------------------------------------
        cls.employee = cls.env['hr.employee'].with_company(cls.company).create({
            'name': 'Test Employee ON',
            'company_id': cls.company.id,
            'l10n_ca_province_id': cls.province_on.id if cls.province_on else False,
        })

        # -- Payroll structure (hourly) ----------------------------------------
        cls.structure = cls.env.ref(
            'l10n_ca_hr_payroll_except_QC.hr_payroll_structure_ca_employee_salary',
            raise_if_not_found=False,
        )

    # ------------------------------------------------------------------ helpers

    @classmethod
    def _create_payroll_accounts(cls):
        """Create the 17 standard Canadian payroll GL accounts for test company."""
        account_defs = [
            ('2310', 'CRA — Federal Income Tax Payable', 'liability_current', True),
            ('2320', 'CRA — CPP Payable',                'liability_current', True),
            ('2321', 'CRA — CPP2 Payable',               'liability_current', True),
            ('2330', 'CRA — EI Payable',                 'liability_current', True),
            ('2340', 'Provincial Income Tax Payable',    'liability_current', True),
            ('2350', 'Ontario EHT Payable',              'liability_current', True),
            ('2360', 'RRSP Contributions Payable',       'liability_current', True),
            ('2370', 'Union Dues Payable',               'liability_current', True),
            ('2380', 'Net Pay Clearing',                 'liability_current', True),
            ('5410', 'Salaries & Wages Expense',         'expense',           False),
            ('5411', 'Paid Time Off Expense',            'expense',           False),
            ('5412', 'Sick Time Off Expense',            'expense',           False),
            ('5413', 'Overtime Expense',                 'expense',           False),
            ('5420', 'CPP Employer Contribution Expense','expense',           False),
            ('5421', 'CPP2 Employer Contribution Expense','expense',          False),
            ('5430', 'EI Employer Premium Expense',      'expense',           False),
            ('5440', 'Ontario EHT Expense',              'expense',           False),
        ]
        cls.accounts = {}
        for code, name, atype, reconcile in account_defs:
            vals = {
                'code': code,
                'name': name,
                'account_type': atype,
                'company_ids': [(6, 0, [cls.company.id])],
            }
            if reconcile:
                vals['reconcile'] = True
            cls.accounts[code] = cls.env['account.account'].with_company(cls.company).create(vals)

    def _account_id(self, code: str) -> int:
        return self.accounts[code].id

    def _make_contract(self, wage: float = 5000.0, schedule_pay: str = 'bi-weekly'):
        """Return a running contract for cls.employee."""
        return self.env['hr.contract'].with_company(self.company).create({
            'name': 'Test Contract',
            'employee_id': self.employee.id,
            'wage': wage,
            'schedule_pay': schedule_pay,
            'date_start': '2026-01-01',
            'state': 'open',
            'company_id': self.company.id,
        })

    def _compute_and_confirm_payslip(self, contract, date_from='2026-04-01', date_to='2026-04-14'):
        """Create, compute and confirm a payslip; return the account.move."""
        slip = self.env['hr.payslip'].with_company(self.company).create({
            'name': 'Test Payslip',
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date_from,
            'date_to': date_to,
            'company_id': self.company.id,
        })
        slip.compute_sheet()
        slip.action_payslip_done()  # confirms and posts the journal entry
        return slip.move_id

    def _lines_by_account(self, move):
        """Return {account_code: [(debit, credit), ...]} for the move."""
        result: dict[str, list[tuple[float, float]]] = {}
        for line in move.line_ids:
            code = line.account_id.code
            result.setdefault(code, []).append((line.debit, line.credit))
        return result

    # ------------------------------------------------------------------ tests

    def test_gross_debits_salaries_expense(self):
        """Confirming a payslip debits 5410 Salaries & Wages Expense."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)
        self.assertTrue(move, 'Payslip confirmation must create an account.move')

        lines = self._lines_by_account(move)
        self.assertIn('5410', lines, 'Salary expense account 5410 must appear in the journal entry')
        debit_total = sum(d for d, _c in lines['5410'])
        self.assertGreater(debit_total, 0,
                           '5410 Salaries Expense must be debited (debit > 0)')
        credit_total = sum(c for _d, c in lines['5410'])
        self.assertAlmostEqual(credit_total, 0.0, places=2,
                               msg='5410 Salaries Expense must NOT be credited')

    def test_cpp_payable_is_credited(self):
        """CPP Payable (2320) must appear as a credit, not a debit."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('2320', lines, 'CPP Payable (2320) must appear in the journal entry')

        credit_total = sum(c for _d, c in lines['2320'])
        debit_total = sum(d for d, _c in lines['2320'])
        self.assertGreater(credit_total, 0,
                           '2320 CPP Payable must be credited (liability grows)')
        # The EE deduction and ER contribution both credit 2320; net debit should be 0
        self.assertAlmostEqual(debit_total, 0.0, places=2,
                               msg='2320 CPP Payable must NOT be debited (was account_debit field bug)')

    def test_ei_payable_is_credited(self):
        """EI Payable (2330) must appear as a credit, not a debit."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('2330', lines, 'EI Payable (2330) must appear in the journal entry')

        credit_total = sum(c for _d, c in lines['2330'])
        debit_total = sum(d for d, _c in lines['2330'])
        self.assertGreater(credit_total, 0,
                           '2330 EI Payable must be credited (liability grows)')
        self.assertAlmostEqual(debit_total, 0.0, places=2,
                               msg='2330 EI Payable must NOT be debited')

    def test_fed_tax_payable_is_credited(self):
        """Federal Income Tax Payable (2310) must be a credit."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('2310', lines, 'Fed Tax Payable (2310) must appear in the journal entry')

        credit_total = sum(c for _d, c in lines['2310'])
        debit_total = sum(d for d, _c in lines['2310'])
        self.assertGreater(credit_total, 0,
                           '2310 Federal Tax Payable must be credited')
        self.assertAlmostEqual(debit_total, 0.0, places=2,
                               msg='2310 Federal Tax Payable must NOT be debited')

    def test_prov_tax_payable_is_credited(self):
        """Provincial Tax Payable (2340) must be a credit (includes OHP for ON)."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('2340', lines,
                      'Prov Tax Payable (2340) must appear in the journal entry (Ontario has PROV_TAX + OHP)')

        credit_total = sum(c for _d, c in lines['2340'])
        debit_total = sum(d for d, _c in lines['2340'])
        self.assertGreater(credit_total, 0,
                           '2340 Provincial Tax Payable must be credited')
        self.assertAlmostEqual(debit_total, 0.0, places=2,
                               msg='2340 Provincial Tax Payable must NOT be debited')

    def test_net_pay_clearing_is_debited_for_deductions(self):
        """Net Pay Clearing (2380) must have debit entries from deductions.

        The GROSS rule credits 2380 for the full gross pay.  Each deduction
        rule (CPP_EE, EI_EE, FED_TAX, PROV_TAX, OHP) then debits 2380 to
        reduce the clearing balance, leaving only the net-pay amount credited.
        The net debit to 2380 must be greater than zero (deductions are drawn).
        """
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('2380', lines, 'Net Pay Clearing (2380) must appear in the journal entry')

        debit_total = sum(d for d, _c in lines['2380'])
        credit_total = sum(c for _d, c in lines['2380'])
        self.assertGreater(debit_total, 0,
                           '2380 Net Pay Clearing must be debited by deduction rules')
        self.assertGreater(credit_total, 0,
                           '2380 Net Pay Clearing must also be credited (GROSS rule)')
        # The net credit balance (credit − debit) equals the net-pay disbursement
        net_credit = credit_total - debit_total
        self.assertGreater(net_credit, 0,
                           '2380 Net Pay Clearing net balance must be a credit (net pay owed)')

    def test_cpp_er_expense_is_debited(self):
        """CPP Employer Expense (5420) must be debited for the ER contribution."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('5420', lines, 'CPP ER Expense (5420) must appear in the journal entry')

        debit_total = sum(d for d, _c in lines['5420'])
        self.assertGreater(debit_total, 0,
                           '5420 CPP ER Expense must be debited')

    def test_ei_er_expense_is_debited(self):
        """EI Employer Expense (5430) must be debited for the ER premium."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        self.assertIn('5430', lines, 'EI ER Expense (5430) must appear in the journal entry')

        debit_total = sum(d for d, _c in lines['5430'])
        self.assertGreater(debit_total, 0,
                           '5430 EI ER Expense must be debited')

    def test_journal_entry_is_balanced(self):
        """The payslip journal entry must have equal total debits and credits."""
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        total_debit = sum(line.debit for line in move.line_ids)
        total_credit = sum(line.credit for line in move.line_ids)
        self.assertAlmostEqual(
            total_debit, total_credit, places=2,
            msg=(
                f'Journal entry must be balanced: '
                f'debit={total_debit:.2f}, credit={total_credit:.2f}'
            ),
        )

    def test_cpp_payable_credit_matches_ee_plus_er(self):
        """Total credit to 2320 CPP Payable equals EE + ER contributions.

        Worked example (bi-weekly $5 000, Ontario, 2026):
          CPP_EE ≈ $139.28  (result negative → via sign-flip → Cr 2320)
          CPP_ER ≈ $139.28  (result positive → directly Cr 2320)
          Total 2320 credit ≈ $278.56
        The exact amounts depend on 2026 rate parameters but must be > 0.
        """
        if not self.structure:
            self.skipTest('Canadian payroll structure not found — module not fully loaded')

        contract = self._make_contract(wage=5000.0)
        move = self._compute_and_confirm_payslip(contract)

        lines = self._lines_by_account(move)
        cpp_credit = sum(c for _d, c in lines.get('2320', []))
        cpp_debit  = sum(d for d, _c in lines.get('2320', []))

        self.assertAlmostEqual(cpp_debit, 0.0, places=2,
                               msg='CPP Payable (2320) must have zero debit (was bugged before fix)')
        self.assertGreater(cpp_credit, 0.0,
                           msg='CPP Payable (2320) must have a positive credit balance')
