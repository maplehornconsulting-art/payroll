# Part of MHC. See LICENSE file for full copyright and licensing details.

import base64
from lxml import etree

from odoo import api, fields, models


class HrPayrollRoe(models.Model):
    _name = 'hr.payroll.roe'
    _description = 'Record of Employment (ROE)'
    _order = 'last_day_paid desc, employee_id'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
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
    serial_number = fields.Char(string='Serial Number')
    first_day_worked = fields.Date(string='First Day Worked')
    last_day_paid = fields.Date(string='Last Day Paid', required=True)
    final_pay_period_end = fields.Date(string='Final Pay Period End Date')
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
    )
    expected_recall = fields.Boolean(string='Expected to Recall')
    expected_recall_date = fields.Date(string='Expected Recall Date')
    total_insurable_hours = fields.Float(string='Total Insurable Hours')
    total_insurable_earnings = fields.Monetary(
        string='Total Insurable Earnings',
        currency_field='currency_id',
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
    period_ids = fields.One2many(
        'hr.payroll.roe.period',
        'roe_id',
        string='Insurable Earnings by Period',
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

    @api.depends('employee_id', 'last_day_paid')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name or ''
            last_day = str(rec.last_day_paid) if rec.last_day_paid else ''
            rec.name = 'ROE - %s - %s' % (emp_name, last_day)

    def action_compute(self):
        for rec in self:
            if not rec.last_day_paid:
                continue
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('state', 'in', ['done', 'paid']),
                ('date_to', '<=', rec.last_day_paid),
            ], order='date_to desc')

            total_earnings = 0.0
            total_hours = 0.0
            for slip in payslips:
                for line in slip.line_ids:
                    if line.code == 'GROSS':
                        total_earnings += abs(line.total)
                total_hours += slip.worked_days_line_ids and sum(
                    wd.number_of_hours for wd in slip.worked_days_line_ids
                ) or 0.0

            rec.total_insurable_earnings = total_earnings
            rec.total_insurable_hours = total_hours

            # Create period breakdown (most recent first, up to 27 periods)
            rec.period_ids.unlink()
            period_payslips = payslips[:27]
            period_vals = []
            for idx, slip in enumerate(period_payslips):
                slip_earnings = sum(
                    abs(line.total) for line in slip.line_ids if line.code == 'GROSS'
                )
                slip_hours = sum(
                    wd.number_of_hours for wd in slip.worked_days_line_ids
                ) if slip.worked_days_line_ids else 0.0
                period_vals.append({
                    'roe_id': rec.id,
                    'period_number': idx + 1,
                    'period_start': slip.date_from,
                    'period_end': slip.date_to,
                    'insurable_earnings': slip_earnings,
                    'insurable_hours': slip_hours,
                })
            if period_vals:
                self.env['hr.payroll.roe.period'].create(period_vals)

    def action_export_xml(self):
        self.ensure_one()
        root = etree.Element('ROESubmission')

        roe_elem = etree.SubElement(root, 'ROE')
        self._add_xml_element(roe_elem, 'SerialNumber', self.serial_number)
        self._add_xml_element(roe_elem, 'PayPeriodType', self.pay_period_type)

        emp = self.employee_id
        empe_elem = etree.SubElement(roe_elem, 'Employee')
        self._add_xml_element(empe_elem, 'Name', emp.name or '')
        self._add_xml_element(empe_elem, 'SIN', emp.l10n_ca_sin or '')

        if emp.private_street or emp.private_city:
            addr_elem = etree.SubElement(empe_elem, 'Address')
            if emp.private_street:
                self._add_xml_element(addr_elem, 'Street', emp.private_street)
            if emp.private_city:
                self._add_xml_element(addr_elem, 'City', emp.private_city)
            if emp.private_state_id:
                self._add_xml_element(addr_elem, 'Province', emp.private_state_id.code)
            if emp.private_zip:
                self._add_xml_element(addr_elem, 'PostalCode', emp.private_zip)

        if self.first_day_worked:
            self._add_xml_element(roe_elem, 'FirstDayWorked', str(self.first_day_worked))
        self._add_xml_element(roe_elem, 'LastDayPaid', str(self.last_day_paid))
        if self.final_pay_period_end:
            self._add_xml_element(roe_elem, 'FinalPayPeriodEnd', str(self.final_pay_period_end))
        self._add_xml_element(roe_elem, 'ReasonCode', self.reason_code)

        if self.total_insurable_hours:
            elem = etree.SubElement(roe_elem, 'TotalInsurableHours')
            elem.text = '%.2f' % self.total_insurable_hours
        if self.total_insurable_earnings:
            elem = etree.SubElement(roe_elem, 'TotalInsurableEarnings')
            elem.text = '%.2f' % self.total_insurable_earnings

        if self.expected_recall:
            self._add_xml_element(roe_elem, 'ExpectedRecall', 'Y')
            if self.expected_recall_date:
                self._add_xml_element(roe_elem, 'ExpectedRecallDate', str(self.expected_recall_date))

        if self.period_ids:
            periods_elem = etree.SubElement(roe_elem, 'InsurableEarningsByPeriod')
            for period in self.period_ids.sorted('period_number'):
                period_elem = etree.SubElement(periods_elem, 'Period')
                self._add_xml_element(period_elem, 'PeriodNumber', str(period.period_number))
                if period.period_start:
                    self._add_xml_element(period_elem, 'StartDate', str(period.period_start))
                if period.period_end:
                    self._add_xml_element(period_elem, 'EndDate', str(period.period_end))
                if period.insurable_earnings:
                    elem = etree.SubElement(period_elem, 'Earnings')
                    elem.text = '%.2f' % period.insurable_earnings
                if period.insurable_hours:
                    elem = etree.SubElement(period_elem, 'Hours')
                    elem.text = '%.2f' % period.insurable_hours

        xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        emp_name = (self.employee_id.name or 'Employee').replace(' ', '_')
        filename = 'ROE_%s_%s.xml' % (emp_name, str(self.last_day_paid))
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(xml_bytes),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/xml',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _add_xml_element(self, parent, tag, value):
        if value:
            elem = etree.SubElement(parent, tag)
            elem.text = str(value)

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_send(self):
        self.write({'state': 'sent'})


class HrPayrollRoePeriod(models.Model):
    _name = 'hr.payroll.roe.period'
    _description = 'ROE Insurable Earnings Period'
    _order = 'period_number'

    roe_id = fields.Many2one(
        'hr.payroll.roe',
        string='ROE',
        required=True,
        ondelete='cascade',
    )
    period_number = fields.Integer(string='Period Number')
    period_start = fields.Date(string='Period Start')
    period_end = fields.Date(string='Period End')
    insurable_earnings = fields.Monetary(
        string='Insurable Earnings',
        currency_field='currency_id',
    )
    insurable_hours = fields.Float(string='Insurable Hours')
    currency_id = fields.Many2one(
        related='roe_id.currency_id',
        string='Currency',
        readonly=True,
    )
