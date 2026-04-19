# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Tests for l10n_ca_hr_payroll_remittance.

These tests are Odoo ORM-level integration tests. They require a running Odoo
instance with the l10n_ca_hr_payroll_remittance module installed.

Test IDs map to the acceptance criteria in the problem statement:
  1. Setup — company + config
  2. Cron creates draft remittance
  3. Aggregation correctness
  4. Confirm + Pay
  5. Late warning
  6. T4 reconciliation
  7. Idempotency
  8. EHT annual remittance
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ca_remittance')
class TestRemittance(TransactionCase):
    """Integration tests for the Canadian payroll remittance workflow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # -- Company ----------------------------------------------------------
        ca_country = cls.env.ref('base.ca')
        cls.company = cls.env['res.company'].create({
            'name': 'Acme Payroll Test Inc.',
            'country_id': ca_country.id,
            'currency_id': cls.env.ref('base.CAD').id,
        })

        # -- CRA Partner ------------------------------------------------------
        cls.cra_partner = cls.env['res.partner'].create({
            'name': 'Receiver General for Canada',
            'is_company': True,
            'supplier_rank': 1,
            'country_id': ca_country.id,
        })

        # -- Bank journal -----------------------------------------------------
        cls.bank_journal = cls.env['account.journal'].with_company(cls.company).create({
            'name': 'Test Bank',
            'type': 'bank',
            'code': 'TBNK',
            'company_id': cls.company.id,
        })

        # -- Remittance config ------------------------------------------------
        cls.config = cls.env['l10n.ca.remittance.config'].create({
            'company_id': cls.company.id,
            'remitter_type': 'regular',
            'cra_business_number': '123456789RP0001',
            'cra_partner_id': cls.cra_partner.id,
            'default_bank_journal_id': cls.bank_journal.id,
            'auto_create_remittances': True,
        })

        # -- GL accounts (normally created by _post_init_hook) ----------------
        cls._ensure_payroll_accounts()

        # -- SAL journal ------------------------------------------------------
        cls.sal_journal = cls.env['account.journal'].search([
            ('code', '=', 'SAL'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        if not cls.sal_journal:
            cls.sal_journal = cls.env['account.journal'].with_company(cls.company).create({
                'name': 'Salary Journal',
                'type': 'general',
                'code': 'SAL',
                'company_id': cls.company.id,
            })

    @classmethod
    def _ensure_payroll_accounts(cls):
        """Create minimal payroll GL accounts for test company."""
        account_defs = [
            ('2310', 'CRA — Federal Income Tax Payable', 'liability_current', True),
            ('2320', 'CPP Payable', 'liability_current', True),
            ('2321', 'CPP2 Payable', 'liability_current', True),
            ('2330', 'EI Payable', 'liability_current', True),
            ('2340', 'Provincial Tax Payable', 'liability_current', True),
            ('2350', 'EHT Payable', 'liability_current', True),
            ('2360', 'RRSP Payable', 'liability_current', True),
            ('2370', 'Union Dues Payable', 'liability_current', True),
            ('2380', 'Net Pay Clearing', 'liability_current', True),
            ('5410', 'Salaries Expense', 'expense', False),
            ('5420', 'CPP ER Expense', 'expense', False),
            ('5430', 'EI ER Expense', 'expense', False),
        ]
        existing = {
            a.code: a
            for a in cls.env['account.account'].search([
                ('company_id', '=', cls.company.id)
            ])
        }
        cls.accounts = dict(existing)
        for code, name, atype, reconcile in account_defs:
            if code not in existing:
                vals = {
                    'code': code, 'name': name, 'account_type': atype,
                    'company_id': cls.company.id,
                }
                if reconcile:
                    vals['reconcile'] = True
                cls.accounts[code] = cls.env['account.account'].with_company(cls.company).create(vals)

    def _make_payslip_move(self, fed_tax, cpp_ee, cpp_er, ei_ee, ei_er, gross, pay_date):
        """Create a posted account.move simulating a payslip posting.

        Entries:
          Dr 5410 (Salaries Expense)     × gross + cpp_er + ei_er
          Cr 2310 (Fed Tax)              × fed_tax
          Cr 2320 (CPP)                  × cpp_ee + cpp_er
          Cr 2330 (EI)                   × ei_ee + ei_er
          Cr 2380 (Net Pay Clearing)     × net

        This is a simplified version of what hr_payroll_account generates.
        """
        net = gross - fed_tax - cpp_ee - ei_ee
        total_debit = gross + cpp_er + ei_er
        total_credit = fed_tax + (cpp_ee + cpp_er) + (ei_ee + ei_er) + net

        move = self.env['account.move'].with_company(self.company).create({
            'journal_id': self.sal_journal.id,
            'date': pay_date,
            'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'account_id': self.accounts['5410'].id, 'debit': total_debit, 'credit': 0.0, 'name': 'Salaries Expense'}),
                (0, 0, {'account_id': self.accounts['2310'].id, 'debit': 0.0, 'credit': fed_tax, 'name': 'Federal Tax'}),
                (0, 0, {'account_id': self.accounts['2320'].id, 'debit': 0.0, 'credit': cpp_ee + cpp_er, 'name': 'CPP'}),
                (0, 0, {'account_id': self.accounts['2330'].id, 'debit': 0.0, 'credit': ei_ee + ei_er, 'name': 'EI'}),
                (0, 0, {'account_id': self.accounts['2380'].id, 'debit': 0.0, 'credit': net, 'name': 'Net Pay'}),
            ],
        })
        move.action_post()
        return move

    def _make_payslip(self, employee, date_from, date_to, move):
        """Create a 'done' payslip record linked to a move."""
        payslip = self.env['hr.payslip'].with_company(self.company).create({
            'name': f'Payslip {date_from}',
            'employee_id': employee.id,
            'date_from': date_from,
            'date_to': date_to,
            'company_id': self.company.id,
            'move_id': move.id,
        })
        # Force state to 'done' bypassing computation
        payslip.write({'state': 'done'})
        return payslip

    def _make_employee(self, name='Test Employee'):
        return self.env['hr.employee'].with_company(self.company).create({
            'name': name,
            'company_id': self.company.id,
        })

    # -------------------------------------------------------------------------
    # Test 1: Setup — basic config creation
    # -------------------------------------------------------------------------

    def test_01_config_created(self):
        """Config record exists with correct BN and remitter type."""
        self.assertEqual(self.config.remitter_type, 'regular')
        self.assertEqual(self.config.cra_business_number, '123456789RP0001')
        self.assertEqual(self.config.company_id, self.company)

    # -------------------------------------------------------------------------
    # Test 2 + 7: Cron creates draft remittance (and idempotency)
    # -------------------------------------------------------------------------

    def test_02_cron_creates_draft_remittance(self):
        """Running the cron creates a cra_pd7a remittance for April 2026."""
        Remittance = self.env['l10n.ca.remittance']
        period_start = date(2026, 4, 1)
        period_end = date(2026, 4, 30)

        # Pre-create with no payslips — cron should skip (already exists)
        # First: ensure no existing record
        Remittance.search([
            ('company_id', '=', self.company.id),
            ('remittance_type', '=', 'cra_pd7a'),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
        ]).unlink()

        # Call _ensure_remittance directly (simulates cron for a specific period)
        rem = Remittance._ensure_remittance(
            self.company, 'cra_pd7a', period_start, period_end
        )

        self.assertEqual(rem.state, 'draft')
        self.assertEqual(rem.remittance_type, 'cra_pd7a')
        self.assertEqual(rem.period_start, period_start)
        self.assertEqual(rem.period_end, period_end)
        # Regular remitter: due on 15th of following month (May 15, 2026)
        self.assertEqual(rem.due_date, date(2026, 5, 15))

    def test_07_cron_idempotency(self):
        """Running _ensure_remittance twice for the same period returns the same record."""
        Remittance = self.env['l10n.ca.remittance']
        period_start = date(2026, 5, 1)
        period_end = date(2026, 5, 31)

        # Clean up
        Remittance.search([
            ('company_id', '=', self.company.id),
            ('remittance_type', '=', 'cra_pd7a'),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
        ]).unlink()

        rem1 = Remittance._ensure_remittance(self.company, 'cra_pd7a', period_start, period_end)
        rem2 = Remittance._ensure_remittance(self.company, 'cra_pd7a', period_start, period_end)
        self.assertEqual(rem1.id, rem2.id, 'Idempotency: same record returned on second call')

        # Verify no duplicate in DB
        count = Remittance.search_count([
            ('company_id', '=', self.company.id),
            ('remittance_type', '=', 'cra_pd7a'),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
        ])
        self.assertEqual(count, 1, 'Only one remittance record should exist')

    # -------------------------------------------------------------------------
    # Test 3: Aggregation correctness
    # -------------------------------------------------------------------------

    def test_03_aggregation_correctness(self):
        """4 NS weekly payslips at $1,203.13 gross each — verify line totals.

        Expected per payslip (from CRA 2026 tables for NS, weekly $1203.13 gross):
          Federal tax:  $11.20
          CPP EE:       $63.58
          CPP ER:       $63.58
          EI EE:        $19.61
          EI ER:        $27.46   (× 1.4 factor)
        """
        employee = self._make_employee('NS Employee')
        period_start = date(2026, 4, 1)
        period_end = date(2026, 4, 30)

        # NS weekly payslip figures
        fed_tax_pp = 11.20
        cpp_ee_pp = 63.58
        cpp_er_pp = 63.58
        ei_ee_pp = 19.61
        ei_er_pp = 27.46
        gross_pp = 1203.13

        payslips = []
        pay_dates = [
            date(2026, 4, 4),
            date(2026, 4, 11),
            date(2026, 4, 18),
            date(2026, 4, 25),
        ]
        for pay_date in pay_dates:
            move = self._make_payslip_move(
                fed_tax_pp, cpp_ee_pp, cpp_er_pp, ei_ee_pp, ei_er_pp, gross_pp, pay_date
            )
            slip = self._make_payslip(employee, period_start, pay_date, move)
            payslips.append(slip)

        # Create remittance and attach payslips
        rem = self.env['l10n.ca.remittance'].with_company(self.company).create({
            'company_id': self.company.id,
            'remittance_type': 'cra_pd7a',
            'period_start': period_start,
            'period_end': period_end,
        })
        rem.payslip_ids = self.env['hr.payslip'].browse([s.id for s in payslips])
        rem._generate_lines()

        lines_by_code = {line.account_id.code: line.amount for line in rem.line_ids}

        # Federal Tax: 4 × $11.20 = $44.80
        self.assertAlmostEqual(lines_by_code.get('2310', 0.0), 4 * fed_tax_pp, places=2,
                               msg='Federal tax line mismatch')

        # CPP (EE + ER combined): 4 × ($63.58 + $63.58) = $508.64
        self.assertAlmostEqual(lines_by_code.get('2320', 0.0), 4 * (cpp_ee_pp + cpp_er_pp), places=2,
                               msg='CPP line mismatch')

        # EI (EE + ER): 4 × ($19.61 + $27.46) = $188.28
        self.assertAlmostEqual(lines_by_code.get('2330', 0.0), 4 * (ei_ee_pp + ei_er_pp), places=2,
                               msg='EI line mismatch')

        # Total: $741.72
        expected_total = 4 * (fed_tax_pp + cpp_ee_pp + cpp_er_pp + ei_ee_pp + ei_er_pp)
        self.assertAlmostEqual(rem.total_amount, expected_total, places=2,
                               msg='Total remittance amount mismatch')

    # -------------------------------------------------------------------------
    # Test 4: Confirm + Pay
    # -------------------------------------------------------------------------

    def test_04_confirm_and_pay(self):
        """Confirm remittance, run payment wizard, check payment and state."""
        employee = self._make_employee('Pay Employee')
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)

        move = self._make_payslip_move(11.20, 63.58, 63.58, 19.61, 27.46, 1203.13, date(2026, 6, 14))
        slip = self._make_payslip(employee, period_start, date(2026, 6, 14), move)

        rem = self.env['l10n.ca.remittance'].with_company(self.company).create({
            'company_id': self.company.id,
            'remittance_type': 'cra_pd7a',
            'period_start': period_start,
            'period_end': period_end,
        })
        rem.payslip_ids = slip
        rem._generate_lines()

        # Confirm
        rem.action_confirm()
        self.assertEqual(rem.state, 'confirmed')
        self.assertTrue(rem.move_id, 'Journal entry should be created on confirm')

        # Pay via wizard
        wizard = self.env['l10n.ca.remittance.payment.wizard'].with_company(self.company).create({
            'remittance_id': rem.id,
            'amount': rem.total_amount,
            'payment_date': date(2026, 7, 15),
            'bank_journal_id': self.bank_journal.id,
            'payment_reference': 'PD7A June 2026',
        })
        wizard.action_confirm_payment()

        self.assertEqual(rem.state, 'paid')
        self.assertTrue(rem.payment_id, 'Payment record should be set')
        self.assertAlmostEqual(
            rem.payment_id.amount,
            rem.total_amount,
            places=2,
            msg='Payment amount should equal remittance total',
        )

    # -------------------------------------------------------------------------
    # Test 5: Late warning
    # -------------------------------------------------------------------------

    def test_05_late_warning(self):
        """Remittance with due_date < today appears as overdue."""
        rem = self.env['l10n.ca.remittance'].with_company(self.company).create({
            'company_id': self.company.id,
            'remittance_type': 'cra_pd7a',
            'period_start': date(2020, 1, 1),
            'period_end': date(2020, 1, 31),
            # due_date will be computed as Feb 15, 2020 — well in the past
        })
        self.assertTrue(rem.due_date, 'due_date should be set')
        self.assertTrue(rem.due_date < date.today(), 'due_date should be in the past')

        # is_late is a non-stored computed field — re-read
        rem.invalidate_recordset(['is_late'])
        self.assertTrue(rem.is_late, 'Remittance with past due_date should be late')

        # Appears in late query
        late = self.env['l10n.ca.remittance'].search([
            ('company_id', '=', self.company.id),
            ('due_date', '<', date.today()),
            ('state', 'not in', ('paid', 'cancelled')),
        ])
        self.assertIn(rem, late, 'Late remittance should appear in overdue query')

    # -------------------------------------------------------------------------
    # Test 6: T4 reconciliation
    # -------------------------------------------------------------------------

    def test_06_t4_reconciliation_match(self):
        """T4 totals matching paid PD7A remittances → reconciliation returns match=True."""
        year = 2025
        employee = self._make_employee('T4 Employee')

        # Create a T4 with known totals
        t4 = self.env['hr.payroll.t4'].with_company(self.company).create({
            'year': year,
            'employee_id': employee.id,
            'company_id': self.company.id,
            'box_16_cpp': 100.0,
            'box_18_ei': 50.0,
            'box_22_tax': 200.0,
            'state': 'confirmed',
        })
        t4_total = 350.0  # 100 + 50 + 200

        # Create a paid PD7A remittance totaling the same amount
        # We'll create it with a manual line
        rem = self.env['l10n.ca.remittance'].with_company(self.company).create({
            'company_id': self.company.id,
            'remittance_type': 'cra_pd7a',
            'period_start': date(year, 1, 1),
            'period_end': date(year, 12, 31),
            'state': 'paid',
        })
        self.env['l10n.ca.remittance.line'].create({
            'remittance_id': rem.id,
            'account_id': self.accounts['2310'].id,
            'label': 'Test',
            'amount': 350.0,
        })

        # Reload to pick up computed total
        rem.invalidate_recordset(['total_amount'])

        result = self.env['l10n.ca.remittance'].with_company(self.company).get_t4_reconciliation(year=year)
        self.assertTrue(result['match'], 'T4 and PD7A totals should match')
        self.assertAlmostEqual(result['delta'], 0.0, places=2)

    # -------------------------------------------------------------------------
    # Test 8: EHT annual remittance
    # -------------------------------------------------------------------------

    def test_08_eht_annual_remittance(self):
        """Provincial EHT remittance for 2026 payroll due on 2027-03-15."""
        Remittance = self.env['l10n.ca.remittance']
        period_start = date(2026, 1, 1)
        period_end = date(2026, 12, 31)

        # Clean up if exists
        Remittance.search([
            ('company_id', '=', self.company.id),
            ('remittance_type', '=', 'provincial_eht'),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
        ]).unlink()

        rem = Remittance._ensure_remittance(
            self.company, 'provincial_eht', period_start, period_end
        )

        self.assertEqual(rem.remittance_type, 'provincial_eht')
        self.assertEqual(rem.due_date, date(2027, 3, 15),
                         'EHT due date should be March 15 of following year')
