# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayrollT4Wizard(models.TransientModel):
    _name = 'hr.payroll.t4.wizard'
    _description = 'Generate T4 Slips Wizard'

    year = fields.Integer(
        string='Tax Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    def action_generate(self):
        self.ensure_one()
        summary = self.env['hr.payroll.t4.summary'].create({
            'year': self.year,
            'company_id': self.company_id.id,
        })
        summary.action_generate_t4s()
        return {
            'type': 'ir.actions.act_window',
            'name': 'T4 Summary',
            'res_model': 'hr.payroll.t4.summary',
            'res_id': summary.id,
            'view_mode': 'form',
            'target': 'current',
        }
