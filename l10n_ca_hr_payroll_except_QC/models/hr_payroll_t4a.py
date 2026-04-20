# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayrollT4A(models.Model):
    _name = 'hr.payroll.t4a'
    _description = 'T4A Slip - Statement of Pension, Retirement, Annuity, and Other Income'
    _order = 'year desc, recipient_name'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    year = fields.Integer(
        string='Tax Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    recipient_name = fields.Char(
        string='Recipient Name',
        required=True,
    )
    recipient_sin = fields.Char(string='SIN')
    recipient_bn = fields.Char(string='Recipient Business Number')
    recipient_address = fields.Text(string='Recipient Address')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
    )
    summary_id = fields.Many2one(
        'hr.payroll.t4a.summary',
        string='T4A Summary',
        ondelete='set null',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('sent', 'Sent'),
        ],
        string='Status',
        default='draft',
        required=True,
    )

    # T4A Box fields
    box_016_pension = fields.Monetary(
        string='Box 016: Pension or Superannuation',
        currency_field='currency_id',
    )
    box_018_lump_sum = fields.Monetary(
        string='Box 018: Lump-Sum Payments',
        currency_field='currency_id',
    )
    box_020_self_employed = fields.Monetary(
        string='Box 020: Self-Employed Commissions',
        currency_field='currency_id',
    )
    box_022_tax_deducted = fields.Monetary(
        string='Box 022: Income Tax Deducted',
        currency_field='currency_id',
    )
    box_024_annuities = fields.Monetary(
        string='Box 024: Annuities',
        currency_field='currency_id',
    )
    box_028_other = fields.Monetary(
        string='Box 028: Other Income',
        currency_field='currency_id',
    )
    box_048_fees = fields.Monetary(
        string='Box 048: Fees for Services',
        currency_field='currency_id',
    )

    @api.depends('year', 'recipient_name')
    def _compute_name(self):
        for rec in self:
            rec.name = 'T4A - %s - %s' % (rec.year, rec.recipient_name or '')

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_send(self):
        self.write({'state': 'sent'})
