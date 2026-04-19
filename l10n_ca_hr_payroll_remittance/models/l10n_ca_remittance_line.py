# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class L10nCaRemittanceLine(models.Model):
    """One line per liability account in a remittance record.

    Each line represents the net credit balance on a payroll liability account
    aggregated across all attached payslip journal entries for the period.
    """

    _name = 'l10n.ca.remittance.line'
    _description = 'Canadian Payroll Remittance Line'
    _order = 'remittance_id, account_id'

    remittance_id = fields.Many2one(
        'l10n.ca.remittance',
        string='Remittance',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='remittance_id.company_id',
        string='Company',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='remittance_id.currency_id',
        string='Currency',
        readonly=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Liability Account',
        required=True,
        ondelete='restrict',
        domain="[('company_id', '=', company_id)]",
    )
    label = fields.Char(
        string='Description',
        help='e.g. "Federal Income Tax", "CPP EE+ER", "EI EE+1.4×ER"',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        default=0.0,
    )
