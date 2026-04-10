# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    l10n_ca_cpp_exempt = fields.Boolean(
        string="CPP Exempt",
        help="Check if this employee is exempt from Canada Pension Plan contributions.",
    )
    l10n_ca_ei_exempt = fields.Boolean(
        string="EI Exempt",
        help="Check if this employee is exempt from Employment Insurance premiums.",
    )
    l10n_ca_additional_tax = fields.Float(
        string="Additional Federal Tax Deduction",
        help="Additional amount of federal tax to deduct per pay period (from TD1 Section 2).",
    )
