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
    l10n_ca_apply_bpa_phase_out = fields.Boolean(
        string="Apply Federal BPA Phase-Out",
        default=False,
        help="When ON: federal BPA is phased out for high earners between the 4th "
             "and 5th federal brackets, per CRA T4127 §5.1. Strictly correct, but "
             "over-withholds by up to ~$224/yr for incomes above $181,440.\n\n"
             "When OFF (default): the TD1 amount is honored verbatim. Matches CRA "
             "PDOC, Wave, QuickBooks, ADP, and Ceridian. Slight under-withholding "
             "for very high earners is reconciled on the employee's T1 filing.",
    )
