# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    l10n_ca_sin = fields.Char(
        string="Social Insurance Number (SIN)",
        groups="hr.group_hr_user",
    )
    l10n_ca_td1_claim_code = fields.Selection(
        selection=[
            ('1', 'Claim Code 1 (Basic Personal Amount Only)'),
            ('2', 'Claim Code 2'),
            ('3', 'Claim Code 3'),
            ('4', 'Claim Code 4'),
            ('5', 'Claim Code 5'),
            ('6', 'Claim Code 6'),
            ('7', 'Claim Code 7'),
            ('8', 'Claim Code 8'),
            ('9', 'Claim Code 9'),
            ('10', 'Claim Code 10'),
            ('0', 'Claim Code 0 (No Claim Amount)'),
        ],
        string="Federal TD1 Claim Code",
        default='1',
        groups="hr.group_hr_user",
        help="The claim code from the employee's TD1 form. Determines the federal personal tax credit amount.",
    )
    l10n_ca_province_id = fields.Many2one(
        'res.country.state',
        string="Province of Employment",
        domain="[('country_id.code', '=', 'CA')]",
        groups="hr.group_hr_user",
        help="The Canadian province or territory where the employee works. Used for provincial tax calculations.",
    )
