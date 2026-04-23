# Part of MHC. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nCaRemittancePaymentWizard(models.TransientModel):
    """Wizard to register payment for a confirmed remittance.

    Creates an account.payment to the CRA partner (or appropriate vendor),
    posts the linked journal entry, reconciles, and transitions the remittance
    to state='paid'.
    """

    _name = 'l10n.ca.remittance.payment.wizard'
    _description = 'Register Remittance Payment'

    remittance_id = fields.Many2one(
        'l10n.ca.remittance',
        string='Remittance',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.today,
    )
    bank_journal_id = fields.Many2one(
        'account.journal',
        string='Bank / Cash Journal',
        required=True,
        domain="[('type', 'in', ['bank', 'cash'])]",
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='remittance_id.currency_id',
        string='Currency',
        readonly=True,
    )
    payment_reference = fields.Char(
        string='Payment Reference / Memo',
        help='Reference visible on the bank statement and payment voucher.',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Payee',
        compute='_compute_partner_id',
        readonly=True,
    )

    @api.depends('remittance_id')
    def _compute_partner_id(self):
        for wiz in self:
            config = self.env['l10n.ca.remittance.config'].search(
                [('company_id', '=', wiz.remittance_id.company_id.id)], limit=1
            )
            wiz.partner_id = config.cra_partner_id if config else False

    @api.onchange('remittance_id')
    def _onchange_remittance_id(self):
        if self.remittance_id:
            config = self.env['l10n.ca.remittance.config'].search(
                [('company_id', '=', self.remittance_id.company_id.id)], limit=1
            )
            if config and config.default_bank_journal_id:
                self.bank_journal_id = config.default_bank_journal_id

    def action_confirm_payment(self):
        """Register payment:
        1. Create account.payment for total_amount.
        2. Post the linked remittance journal entry (move_id).
        3. Reconcile the payment move with the remittance move.
        4. Set state='paid'.
        """
        self.ensure_one()
        remittance = self.remittance_id
        if remittance.state != 'confirmed':
            raise UserError(_('The remittance must be in Confirmed state to register payment.'))

        company = remittance.company_id
        config = self.env['l10n.ca.remittance.config'].search(
            [('company_id', '=', company.id)], limit=1
        )
        partner = config.cra_partner_id if config else False

        # Create vendor payment
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': partner.id if partner else False,
            'amount': self.amount,
            'date': self.payment_date,
            'journal_id': self.bank_journal_id.id,
            'currency_id': remittance.currency_id.id,
            'ref': self.payment_reference or remittance.name,
            'company_id': company.id,
        }
        payment = self.env['account.payment'].with_company(company).create(payment_vals)
        payment.action_post()

        # Post the remittance journal entry
        if remittance.move_id and remittance.move_id.state == 'draft':
            remittance.move_id.action_post()

        # Attempt reconciliation of clearing account lines
        self._reconcile_payment_and_move(payment, remittance.move_id)

        remittance.write({
            'state': 'paid',
            'payment_id': payment.id,
        })

        return {'type': 'ir.actions.act_window_close'}

    def _reconcile_payment_and_move(self, payment, move):
        """Reconcile outstanding clearing lines between the payment and remittance move."""
        if not move or move.state != 'posted':
            return

        # Find the credit line in the remittance move (clearing acct 2380)
        rem_lines = move.line_ids.filtered(
            lambda l: l.account_id.reconcile and not l.reconciled and l.credit > 0
        )
        # Find the debit line in the payment's move
        pay_move_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.reconcile and not l.reconciled and l.debit > 0
        ) if payment.move_id else self.env['account.move.line']

        to_reconcile = rem_lines | pay_move_lines
        if to_reconcile:
            try:
                to_reconcile.reconcile()
            except (UserError, ValueError) as exc:
                # Reconciliation is best-effort; log but don't block the payment.
                # Common causes: lines already reconciled, mismatched currencies.
                _logger.warning('Remittance reconciliation skipped: %s', exc)
