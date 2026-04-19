# Part of MHC. See LICENSE file for full copyright and licensing details.

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Regex for CRA Business Number — 9 digits + RT/RP/RC + 4 digits
# Payroll accounts use the RP suffix
_BN_RE = re.compile(r'^\d{9}R[A-Z]\d{4}$')


class L10nCaRemittanceConfig(models.Model):
    """One configuration record per company.

    Stores remitter type, CRA business number, optional provincial accounts,
    default bank journal, and the CRA vendor partner.
    """

    _name = 'l10n.ca.remittance.config'
    _description = 'Canadian Payroll Remittance Configuration'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        ondelete='cascade',
    )
    remitter_type = fields.Selection(
        selection=[
            ('quarterly', 'Quarterly Remitter'),
            ('regular', 'Regular Remitter'),
            ('threshold_1', 'Threshold 1 Accelerated'),
            ('threshold_2', 'Threshold 2 Accelerated'),
        ],
        string='CRA Remitter Type',
        default='regular',
        required=True,
        help=(
            'Determined annually by CRA based on your Average Monthly '
            'Withholding Amount (AMWA) from two years prior:\n'
            '  • Quarterly: AMWA < $3,000\n'
            '  • Regular: AMWA $3,000–$24,999.99\n'
            '  • Threshold 1: AMWA $25,000–$99,999.99\n'
            '  • Threshold 2: AMWA ≥ $100,000'
        ),
    )
    cra_business_number = fields.Char(
        string='CRA Business Number (BN)',
        help='Format: 123456789RP0001',
    )
    eht_account_number = fields.Char(
        string='EHT Account Number',
        help='Ontario / MB / NL Employer Health Tax account number (optional).',
    )
    wcb_account_number = fields.Char(
        string='WCB Account Number',
        help='Provincial Workers Compensation Board account number (optional).',
    )
    wcb_province = fields.Selection(
        selection=[
            ('AB', 'Alberta'),
            ('BC', 'British Columbia'),
            ('MB', 'Manitoba'),
            ('NB', 'New Brunswick'),
            ('NL', 'Newfoundland and Labrador'),
            ('NS', 'Nova Scotia'),
            ('NT', 'Northwest Territories'),
            ('NU', 'Nunavut'),
            ('ON', 'Ontario'),
            ('PE', 'Prince Edward Island'),
            ('SK', 'Saskatchewan'),
            ('YT', 'Yukon'),
        ],
        string='WCB Province',
    )
    default_bank_journal_id = fields.Many2one(
        'account.journal',
        string='Default Bank Journal',
        domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]",
        help='Default journal for remittance payments.',
    )
    cra_partner_id = fields.Many2one(
        'res.partner',
        string='CRA Partner',
        help='Receiver General for Canada — used as the vendor for CRA payments.',
    )
    auto_create_remittances = fields.Boolean(
        string='Auto-Create Remittances',
        default=True,
        help='If enabled, the daily cron will automatically create draft remittance records.',
    )

    _sql_constraints = [
        (
            'company_unique',
            'UNIQUE(company_id)',
            'A remittance configuration already exists for this company.',
        ),
    ]

    @api.constrains('cra_business_number')
    def _check_cra_business_number(self):
        for rec in self:
            if rec.cra_business_number and not _BN_RE.match(rec.cra_business_number):
                raise ValidationError(
                    'CRA Business Number must be in the format 123456789RP0001 '
                    '(9 digits + 2-letter program code + 4 digits). '
                    f'Got: "{rec.cra_business_number}"'
                )
