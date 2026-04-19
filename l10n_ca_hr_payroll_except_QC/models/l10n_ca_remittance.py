# Part of MHC. See LICENSE file for full copyright and licensing details.

from __future__ import annotations

import calendar
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# ---------------------------------------------------------------------------
# Business-day helper
# ---------------------------------------------------------------------------

def _add_business_days(start: date, days: int) -> date:
    """Return *start* + *days* business days, skipping weekends.

    Statutory holidays are not considered (would require locale-specific data).
    """
    result = start
    count = 0
    while count < days:
        result += timedelta(days=1)
        if result.weekday() < 5:  # Mon–Fri
            count += 1
    return result


def _next_business_day(d: date) -> date:
    """If *d* falls on a weekend, advance to the following Monday."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _last_day_of_month(d: date) -> date:
    """Return the last calendar day of the month containing *d*."""
    last = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last)


# Liability account codes that belong to each remittance type
REMITTANCE_ACCOUNT_CODES = {
    'cra_pd7a': ['2310', '2320', '2321', '2330'],
    'provincial_eht': ['2350'],
    'wcb': [],
    'rrsp': ['2360'],
    'union_dues': ['2370'],
    'garnishment': [],
}


class L10nCaRemittance(models.Model):
    """One remittance record per period per type per company.

    Tracks what is owed to CRA / provincial agencies / third parties,
    aggregates liability balances from payslip journal entries, and manages
    the confirm → pay workflow.
    """

    _name = 'l10n.ca.remittance'
    _description = 'Canadian Payroll Remittance'
    _order = 'period_start desc, remittance_type'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------
    # Core fields
    # ------------------------------------------------------------------

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    remittance_type = fields.Selection(
        selection=[
            ('cra_pd7a', 'CRA — PD7A (Federal Source Deductions)'),
            ('provincial_eht', 'Provincial EHT'),
            ('wcb', 'WCB / WorkSafeBC'),
            ('rrsp', 'RRSP Contributions'),
            ('union_dues', 'Union Dues'),
            ('garnishment', 'Garnishment / Court Order'),
        ],
        string='Remittance Type',
        required=True,
        tracking=True,
    )
    period_start = fields.Date(
        string='Period Start',
        required=True,
    )
    period_end = fields.Date(
        string='Period End',
        required=True,
    )
    due_date = fields.Date(
        string='Due Date',
        compute='_compute_due_date',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('paid', 'Paid'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    payslip_ids = fields.Many2many(
        'hr.payslip',
        'l10n_ca_remittance_payslip_rel',
        'remittance_id',
        'payslip_id',
        string='Payslips',
        domain="[('state', '=', 'done'), ('company_id', '=', company_id)]",
    )
    line_ids = fields.One2many(
        'l10n.ca.remittance.line',
        'remittance_id',
        string='Remittance Lines',
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
    )
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        readonly=True,
        copy=False,
    )
    notes = fields.Html(
        string='Notes',
    )
    is_late = fields.Boolean(
        string='Overdue',
        compute='_compute_is_late',
        store=False,
    )

    _sql_constraints = [
        (
            'unique_period',
            'UNIQUE(company_id, remittance_type, period_start, period_end)',
            'A remittance record already exists for this company, type, and period.',
        ),
    ]

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('company_id', 'remittance_type', 'period_start', 'period_end')
    def _compute_name(self):
        type_labels = dict(self._fields['remittance_type'].selection)
        for rec in self:
            type_label = type_labels.get(rec.remittance_type, rec.remittance_type or '')
            period = ''
            if rec.period_start and rec.period_end:
                period = f'{rec.period_start.strftime("%Y-%m")} '
            company_name = rec.company_id.name or ''
            rec.name = f'{type_label} {period} — {company_name}'.strip()

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))

    @api.depends('remittance_type', 'period_end')
    def _compute_due_date(self):
        """Compute due date per CRA remittance schedule.

        See schedule table in the problem statement for full rules.
        """
        for rec in self:
            rec.due_date = rec._calc_due_date()

    def _calc_due_date(self) -> date | bool:
        """Return the computed due date for this remittance, or False."""
        if not self.period_end:
            return False

        rtype = self.remittance_type
        period_end = self.period_end

        # Determine remitter_type from config
        config = self.env['l10n.ca.remittance.config'].search(
            [('company_id', '=', self.company_id.id)], limit=1
        )
        remitter_type = config.remitter_type if config else 'regular'

        if rtype == 'cra_pd7a':
            if remitter_type == 'quarterly':
                # 15th of month after quarter-end (Apr 15 / Jul 15 / Oct 15 / Jan 15)
                q_end_months = {3: 4, 6: 7, 9: 10, 12: 1}
                q_month = q_end_months.get(period_end.month)
                if q_month is None:
                    # Not a quarter-end month — use next month
                    q_month = (period_end.month % 12) + 1
                q_year = period_end.year if q_month != 1 else period_end.year + 1
                due = date(q_year, q_month, 15)

            elif remitter_type == 'regular':
                # 15th of month following period_end
                next_m = (period_end.month % 12) + 1
                next_y = period_end.year if next_m != 1 else period_end.year + 1
                due = date(next_y, next_m, 15)

            elif remitter_type == 'threshold_1':
                # 25th (1st–15th payroll) or 10th of next month (16th–EOM payroll)
                if period_end.day <= 15:
                    due = date(period_end.year, period_end.month, 25)
                else:
                    next_m = (period_end.month % 12) + 1
                    next_y = period_end.year if next_m != 1 else period_end.year + 1
                    due = date(next_y, next_m, 10)

            elif remitter_type == 'threshold_2':
                # period_end + 3 business days
                due = _add_business_days(period_end, 3)
                return due  # already a business day

            else:
                due = period_end + timedelta(days=15)

        elif rtype == 'provincial_eht':
            # March 15 of year following period_end.year (Ontario annual)
            due = date(period_end.year + 1, 3, 15)

        elif rtype == 'wcb':
            # Last day of month following quarter-end
            q_end_months = {3: 4, 6: 7, 9: 10, 12: 1}
            follow_m = q_end_months.get(period_end.month)
            if follow_m is None:
                follow_m = (period_end.month % 12) + 1
            follow_y = period_end.year if follow_m != 1 else period_end.year + 1
            due = _last_day_of_month(date(follow_y, follow_m, 1))

        elif rtype == 'rrsp':
            # period_end + 30 days
            due = period_end + timedelta(days=30)

        elif rtype == 'union_dues':
            # 15th of month following period_end
            next_m = (period_end.month % 12) + 1
            next_y = period_end.year if next_m != 1 else period_end.year + 1
            due = date(next_y, next_m, 15)

        elif rtype == 'garnishment':
            # period_end + 7 days
            due = period_end + timedelta(days=7)

        else:
            due = period_end + timedelta(days=15)

        return _next_business_day(due)

    @api.depends('due_date', 'state')
    def _compute_is_late(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_late = bool(
                rec.due_date and rec.due_date < today and rec.state not in ('paid', 'cancelled')
            )

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    def action_confirm(self):
        """Draft → Confirmed.

        Validates total > 0, generates a draft journal entry to clear liabilities.
        """
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft remittances can be confirmed.'))
            if not rec.total_amount or rec.total_amount <= 0:
                raise UserError(
                    _('Cannot confirm a remittance with zero total. Please attach payslips and generate lines first.')
                )
            move = rec._create_remittance_move()
            rec.write({'state': 'confirmed', 'move_id': move.id})

    def action_cancel(self):
        """Draft / Confirmed → Cancelled.

        Reverses any draft journal entries.
        """
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_('A paid remittance cannot be cancelled.'))
            if rec.move_id and rec.move_id.state == 'draft':
                rec.move_id.button_cancel()
            rec.write({'state': 'cancelled'})

    def action_reset_draft(self):
        """Cancelled → Draft."""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled remittances can be reset to draft.'))
            rec.write({'state': 'draft'})

    def action_generate_lines(self):
        """Regenerate remittance lines from attached payslips."""
        for rec in self:
            if rec.state not in ('draft',):
                raise UserError(_('Lines can only be regenerated on draft remittances.'))
            rec._generate_lines()

    def action_open_payment_wizard(self):
        """Open the payment wizard to mark remittance as paid."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('The remittance must be confirmed before payment.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Remittance Payment'),
            'res_model': 'l10n.ca.remittance.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_remittance_id': self.id,
                'default_amount': self.total_amount,
            },
        }

    def action_export_pd7a_csv(self):
        """Export a PD7A-compatible CSV file.

        # DRAFT FORMAT — verify against CRA T4127 Appendix C spec before production use.
        # Columns: BN, period_start, period_end, fed_tax, cpp_total, ei_total,
        #          gross_payroll, employee_count
        """
        self.ensure_one()
        import base64
        import io
        import csv

        config = self.env['l10n.ca.remittance.config'].search(
            [('company_id', '=', self.company_id.id)], limit=1
        )
        bn = config.cra_business_number if config else ''

        lines_by_acct = {line.account_id.code: line.amount for line in self.line_ids}
        fed_tax = lines_by_acct.get('2310', 0.0)
        cpp_total = lines_by_acct.get('2320', 0.0) + lines_by_acct.get('2321', 0.0)
        ei_total = lines_by_acct.get('2330', 0.0)

        # Gross payroll and employee count from payslips
        gross = sum(
            abs(line.total)
            for slip in self.payslip_ids
            for line in slip.line_ids
            if line.code == 'GROSS'
        )
        emp_count = len(self.payslip_ids.mapped('employee_id'))

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['BN', 'period_start', 'period_end', 'fed_tax', 'cpp_total',
                         'ei_total', 'gross_payroll', 'employee_count'])
        writer.writerow([
            bn,
            self.period_start.isoformat() if self.period_start else '',
            self.period_end.isoformat() if self.period_end else '',
            f'{fed_tax:.2f}',
            f'{cpp_total:.2f}',
            f'{ei_total:.2f}',
            f'{gross:.2f}',
            emp_count,
        ])

        csv_bytes = buf.getvalue().encode('utf-8')
        attachment = self.env['ir.attachment'].create({
            'name': f'pd7a_{self.period_start}_{self.period_end}.csv',
            'type': 'binary',
            'datas': base64.b64encode(csv_bytes).decode('ascii'),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_lines(self):
        """(Re)generate remittance lines by aggregating payslip journal entries."""
        self.ensure_one()
        account_codes = REMITTANCE_ACCOUNT_CODES.get(self.remittance_type, [])
        if not account_codes:
            return

        # Remove existing lines
        self.line_ids.unlink()

        # Collect all posted account.move.line records from payslip moves
        move_line_model = self.env['account.move.line']
        payslip_moves = self.payslip_ids.mapped('move_id').filtered(
            lambda m: m.state == 'posted'
        )
        if not payslip_moves:
            return

        # Lookup accounts by code for this company
        accounts = self.env['account.account'].search([
            ('code', 'in', account_codes),
            ('company_id', '=', self.company_id.id),
        ])
        account_map = {acct.code: acct for acct in accounts}

        lines_to_create = []
        for code in account_codes:
            acct = account_map.get(code)
            if not acct:
                continue
            move_lines = move_line_model.search([
                ('move_id', 'in', payslip_moves.ids),
                ('account_id', '=', acct.id),
            ])
            if not move_lines:
                continue
            # Net credit balance = credits − debits (liabilities accumulate as credits)
            net_credit = sum(ml.credit - ml.debit for ml in move_lines)
            if not net_credit:
                continue
            label = acct.name
            lines_to_create.append({
                'remittance_id': self.id,
                'account_id': acct.id,
                'label': label,
                'amount': net_credit,
            })

        if lines_to_create:
            self.env['l10n.ca.remittance.line'].create(lines_to_create)

    def _create_remittance_move(self):
        """Create a draft journal entry to clear liability accounts.

        For each line: Dr <liability account> × amount
        Cr Suspense (Net Pay Clearing 2380) × total
        """
        # Find SAL journal
        journal = self.env['account.journal'].search([
            ('code', '=', 'SAL'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        if not journal:
            raise UserError(_('No suitable journal found. Please configure the SAL journal.'))

        # Suspense / clearing account (2380)
        clearing_acct = self.env['account.account'].search([
            ('code', '=', '2380'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not clearing_acct:
            raise UserError(_('Account 2380 (Net Pay Clearing) not found. Please run the accounting setup.'))

        move_lines = []
        for line in self.line_ids:
            # Debit the liability account (to clear it)
            move_lines.append((0, 0, {
                'account_id': line.account_id.id,
                'name': line.label or line.account_id.name,
                'debit': line.amount,
                'credit': 0.0,
            }))

        # Credit the clearing account
        move_lines.append((0, 0, {
            'account_id': clearing_acct.id,
            'name': _('Remittance to CRA — %s') % (self.name or ''),
            'debit': 0.0,
            'credit': self.total_amount,
        }))

        move = self.env['account.move'].with_company(self.company_id).create({
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': self.name,
            'line_ids': move_lines,
            'company_id': self.company_id.id,
        })
        return move

    # ------------------------------------------------------------------
    # Cron entry point
    # ------------------------------------------------------------------

    @api.model
    def _cron_create_remittances(self):
        """Daily cron: create draft remittances for all companies with auto_create=True."""
        RemConfig = self.env['l10n.ca.remittance.config']
        configs = RemConfig.search([('auto_create_remittances', '=', True)])
        today = fields.Date.today()
        for config in configs:
            self._create_pending_remittances(config, today)

    @api.model
    def _create_pending_remittances(self, config, today=None):
        """Create draft remittance records for periods not yet covered.

        Called by the cron for a single company config.
        """
        if today is None:
            today = fields.Date.today()

        company = config.company_id

        # Determine the current period boundaries
        period_start, period_end = self._current_period_bounds(config, today)
        if not period_start or not period_end:
            return

        # CRA PD7A
        self._ensure_remittance(
            company, 'cra_pd7a', period_start, period_end
        )

        # Provincial EHT (annual — year boundary)
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)
        self._ensure_remittance(
            company, 'provincial_eht', year_start, year_end
        )

        # RRSP — same period as payroll
        self._ensure_remittance(
            company, 'rrsp', period_start, period_end
        )

        # Union dues — same period as payroll
        self._ensure_remittance(
            company, 'union_dues', period_start, period_end
        )

        # Send late-warning activities
        self._send_due_date_activities(company, today)

    @api.model
    def _current_period_bounds(self, config, today):
        """Return (period_start, period_end) for the current remittance period."""
        rtype = config.remitter_type

        if rtype == 'quarterly':
            # Quarter containing today
            q_start_month = ((today.month - 1) // 3) * 3 + 1
            period_start = date(today.year, q_start_month, 1)
            q_end_month = q_start_month + 2
            last = calendar.monthrange(today.year, q_end_month)[1]
            period_end = date(today.year, q_end_month, last)

        elif rtype == 'threshold_2':
            # Weekly periods (Mon–Sun) — use the previous full week
            dow = today.weekday()
            period_start = today - timedelta(days=dow + 7)
            period_end = period_start + timedelta(days=6)

        elif rtype == 'threshold_1':
            # Semi-monthly (1–15, 16–EOM)
            if today.day <= 15:
                period_start = date(today.year, today.month, 1)
                period_end = date(today.year, today.month, 15)
            else:
                period_start = date(today.year, today.month, 16)
                last = calendar.monthrange(today.year, today.month)[1]
                period_end = date(today.year, today.month, last)

        else:
            # Regular — monthly
            period_start = date(today.year, today.month, 1)
            last = calendar.monthrange(today.year, today.month)[1]
            period_end = date(today.year, today.month, last)

        return period_start, period_end

    @api.model
    def _ensure_remittance(self, company, remittance_type, period_start, period_end):
        """Create a draft remittance if one doesn't already exist for the period."""
        existing = self.search([
            ('company_id', '=', company.id),
            ('remittance_type', '=', remittance_type),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
        ], limit=1)
        if existing:
            return existing

        rem = self.with_company(company).create({
            'company_id': company.id,
            'remittance_type': remittance_type,
            'period_start': period_start,
            'period_end': period_end,
        })

        # Attach eligible payslips
        payslips = self.env['hr.payslip'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'done'),
            ('date_to', '>=', period_start),
            ('date_from', '<=', period_end),
        ])
        if payslips:
            rem.payslip_ids = payslips
            rem._generate_lines()

        return rem

    @api.model
    def _send_due_date_activities(self, company, today):
        """Schedule an activity 5 business days before due_date for upcoming remittances."""
        warning_date = _add_business_days(today, 5)
        remittances = self.search([
            ('company_id', '=', company.id),
            ('state', 'in', ('draft', 'confirmed')),
            ('due_date', '=', warning_date),
        ])
        for rem in remittances:
            # Check if activity already scheduled
            existing_activity = self.env['mail.activity'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', rem.id),
                ('activity_type_id.category', '=', 'default'),
            ], limit=1)
            if not existing_activity:
                rem.activity_schedule(
                    'mail.mail_activity_data_todo',
                    date_deadline=rem.due_date,
                    summary=_('Remittance due in 5 business days'),
                    note=_(
                        'Remittance <b>%s</b> for %s is due on %s. '
                        'Please confirm and submit payment.'
                    ) % (rem.name, company.name, rem.due_date),
                )

    # ------------------------------------------------------------------
    # Dashboard query helpers
    # ------------------------------------------------------------------

    @api.model
    def get_dashboard_data(self):
        """Return aggregated data for the annual reporting dashboard."""
        today = fields.Date.today()
        company_id = self.env.company.id

        # Owing now — all non-paid, non-cancelled
        owing = self.search([
            ('company_id', '=', company_id),
            ('state', 'not in', ('paid', 'cancelled')),
        ])

        # This year
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)
        this_year = self.search([
            ('company_id', '=', company_id),
            ('period_end', '>=', year_start),
            ('period_end', '<=', year_end),
        ])

        # Late
        late = self.search([
            ('company_id', '=', company_id),
            ('due_date', '<', today),
            ('state', 'not in', ('paid', 'cancelled')),
        ])

        return {
            'owing_total': sum(owing.mapped('total_amount')),
            'owing_count': len(owing),
            'this_year_count': len(this_year),
            'this_year_total': sum(this_year.mapped('total_amount')),
            'late_count': len(late),
            'late_ids': late.ids,
        }

    @api.model
    def get_t4_reconciliation(self, year=None):
        """Compare sum of paid CRA PD7A remittances to T4 box totals.

        Returns a dict:
            {
                'match': True/False,
                'delta': float,
                'remittance_total': float,
                't4_total': float,
            }
        """
        if year is None:
            year = fields.Date.today().year
        company_id = self.env.company.id

        # Sum paid PD7A remittances for the year
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        paid_remittances = self.search([
            ('company_id', '=', company_id),
            ('remittance_type', '=', 'cra_pd7a'),
            ('state', '=', 'paid'),
            ('period_end', '>=', year_start),
            ('period_end', '<=', year_end),
        ])
        remittance_total = sum(paid_remittances.mapped('total_amount'))

        # Sum T4 box totals (box 16 CPP + box 18 EI + box 22 Fed Tax)
        t4s = self.env['hr.payroll.t4'].search([
            ('company_id', '=', company_id),
            ('year', '=', year),
            ('state', 'in', ('confirmed', 'sent')),
        ])
        t4_total = sum(
            (t4.box_16_cpp or 0.0)
            + (t4.box_18_ei or 0.0)
            + (t4.box_22_tax or 0.0)
            for t4 in t4s
        )

        delta = abs(remittance_total - t4_total)
        return {
            'match': delta <= 1.0,
            'delta': delta,
            'remittance_total': remittance_total,
            't4_total': t4_total,
            'year': year,
        }
