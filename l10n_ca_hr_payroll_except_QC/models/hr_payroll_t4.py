# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

# CRA annual maximum insurable/pensionable earnings limits
# Update these constants each year to reflect current CRA limits
T4_MAX_EI_INSURABLE = 68900.00   # Box 24: Maximum EI Insurable Earnings
T4_MAX_CPP_PENSIONABLE = 74600.00  # Box 26: Maximum CPP/QPP Pensionable Earnings


class HrPayrollT4(models.Model):
    _name = 'hr.payroll.t4'
    _description = 'T4 Slip - Statement of Remuneration Paid'
    _order = 'year desc, employee_id'

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
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='restrict',
    )
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
        'hr.payroll.t4.summary',
        string='T4 Summary',
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

    # T4 Box fields
    box_14_employment_income = fields.Monetary(
        string='Box 14: Employment Income',
        currency_field='currency_id',
    )
    box_16_cpp = fields.Monetary(
        string='Box 16: CPP Contributions',
        currency_field='currency_id',
    )
    box_16a_cpp2 = fields.Monetary(
        string='Box 16A: CPP2 Contributions',
        currency_field='currency_id',
    )
    box_17_qpp = fields.Monetary(
        string='Box 17: QPP Contributions',
        currency_field='currency_id',
    )
    box_18_ei = fields.Monetary(
        string='Box 18: EI Premiums',
        currency_field='currency_id',
    )
    box_20_rpp = fields.Monetary(
        string='Box 20: RPP Contributions',
        currency_field='currency_id',
    )
    box_22_tax = fields.Monetary(
        string='Box 22: Income Tax Deducted',
        currency_field='currency_id',
    )
    box_24_ei_insurable = fields.Monetary(
        string='Box 24: EI Insurable Earnings',
        currency_field='currency_id',
    )
    box_26_pensionable = fields.Monetary(
        string='Box 26: CPP/QPP Pensionable Earnings',
        currency_field='currency_id',
    )
    box_44_union = fields.Monetary(
        string='Box 44: Union Dues',
        currency_field='currency_id',
    )
    box_46_donations = fields.Monetary(
        string='Box 46: Charitable Donations',
        currency_field='currency_id',
    )
    box_52_cpp2 = fields.Monetary(
        string='Box 52: CPP2 Employee Contributions',
        currency_field='currency_id',
    )
    province_of_employment = fields.Char(
        string='Province of Employment',
    )
    employee_sin = fields.Char(
        related='employee_id.l10n_ca_sin',
        string='SIN',
        readonly=True,
    )
    employee_address = fields.Text(
        string='Employee Address',
        compute='_compute_employee_address',
        store=True,
    )

    @api.depends('year', 'employee_id')
    def _compute_name(self):
        for rec in self:
            employee_name = rec.employee_id.name or ''
            rec.name = 'T4 - %s - %s' % (rec.year, employee_name)

    @api.depends('employee_id')
    def _compute_employee_address(self):
        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.employee_address = ''
                continue
            parts = []
            if emp.private_street:
                parts.append(emp.private_street)
            if emp.private_street2:
                parts.append(emp.private_street2)
            city_line = ' '.join(filter(None, [
                emp.private_city,
                emp.private_state_id.code if emp.private_state_id else '',
                emp.private_zip,
            ]))
            if city_line.strip():
                parts.append(city_line.strip())
            if emp.private_country_id:
                parts.append(emp.private_country_id.name)
            rec.employee_address = '\n'.join(parts)
    def action_compute(self):
        for rec in self:
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('state', 'in', ['done', 'paid']),
                ('date_from', '>=', '%s-01-01' % rec.year),
                ('date_to', '<=', '%s-12-31' % rec.year),
            ])
            totals = {
                'GROSS': 0.0,
                'CPP_EE': 0.0,
                'CPP2_EE': 0.0,
                'EI_EE': 0.0,
                'RRSP': 0.0,
                'FED_TAX': 0.0,
                'PROV_TAX': 0.0,
                'OHP': 0.0,
                'UNION_DUES': 0.0,
            }
            for slip in payslips:
                for line in slip.line_ids:
                    if line.code in totals:
                        totals[line.code] += abs(line.total)

            box_14 = totals['GROSS']
            box_16 = totals['CPP_EE']
            box_16a = totals['CPP2_EE']
            box_18 = totals['EI_EE']
            box_20 = totals['RRSP']
            box_22 = totals['FED_TAX'] + totals['PROV_TAX'] + totals['OHP']
            box_24 = min(box_14, T4_MAX_EI_INSURABLE)
            box_26 = min(box_14, T4_MAX_CPP_PENSIONABLE)
            box_44 = totals['UNION_DUES']
            box_52 = box_16a

            rec.write({
                'box_14_employment_income': box_14,
                'box_16_cpp': box_16,
                'box_16a_cpp2': box_16a,
                'box_17_qpp': 0.0,
                'box_18_ei': box_18,
                'box_20_rpp': box_20,
                'box_22_tax': box_22,
                'box_24_ei_insurable': box_24,
                'box_26_pensionable': box_26,
                'box_44_union': box_44,
                'box_52_cpp2': box_52,
                'province_of_employment': rec.employee_id.l10n_ca_province_id.code if rec.employee_id.l10n_ca_province_id else '',
            })

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_send(self):
        self.write({'state': 'sent'})
