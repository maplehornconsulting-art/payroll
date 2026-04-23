# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayrollRoeWizard(models.TransientModel):
    _name = 'hr.payroll.roe.wizard'
    _description = 'Create Record of Employment Wizard'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
    )
    last_day_paid = fields.Date(
        string='Last Day Paid',
        required=True,
    )
    reason_code = fields.Selection(
        selection=[
            ('A', 'A - Shortage of Work / End of Contract or Season'),
            ('B', 'B - Strike or Lockout'),
            ('C', 'C - Return to School'),
            ('D', 'D - Illness or Injury'),
            ('E', 'E - Quit'),
            ('F', 'F - Maternity'),
            ('G', 'G - Retirement'),
            ('H', 'H - Work Sharing'),
            ('K', 'K - Other'),
            ('M', 'M - Dismissal / Terminated'),
            ('N', 'N - Leave of Absence'),
            ('P', 'P - Parental'),
            ('Z', 'Z - Compassionate Care'),
        ],
        string='Reason for Issuing',
        required=True,
    )
    pay_period_type = fields.Selection(
        selection=[
            ('W', 'Weekly'),
            ('B', 'Bi-weekly'),
            ('S', 'Semi-monthly'),
            ('M', 'Monthly'),
        ],
        string='Pay Period Type',
        default='B',
    )

    def action_generate(self):
        self.ensure_one()
        roe = self.env['hr.payroll.roe'].create({
            'employee_id': self.employee_id.id,
            'last_day_paid': self.last_day_paid,
            'reason_code': self.reason_code,
            'pay_period_type': self.pay_period_type,
            'company_id': self.employee_id.company_id.id,
        })
        roe.action_compute()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Record of Employment',
            'res_model': 'hr.payroll.roe',
            'res_id': roe.id,
            'view_mode': 'form',
            'target': 'current',
        }
