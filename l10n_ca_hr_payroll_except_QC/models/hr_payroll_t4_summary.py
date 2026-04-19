# Part of MHC. See LICENSE file for full copyright and licensing details.

import base64
from lxml import etree

from odoo import api, fields, models


class HrPayrollT4Summary(models.Model):
    _name = 'hr.payroll.t4.summary'
    _description = 'T4 Summary'
    _order = 'year desc, company_id'

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
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    t4_ids = fields.One2many(
        'hr.payroll.t4',
        'summary_id',
        string='T4 Slips',
    )

    # Computed totals
    total_employees = fields.Integer(
        string='Total Employees',
        compute='_compute_totals',
        store=True,
    )
    total_employment_income = fields.Monetary(
        string='Total Employment Income',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_cpp = fields.Monetary(
        string='Total CPP Contributions',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_cpp2 = fields.Monetary(
        string='Total CPP2 Contributions',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_ei = fields.Monetary(
        string='Total EI Premiums',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_tax = fields.Monetary(
        string='Total Income Tax Deducted',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_rpp = fields.Monetary(
        string='Total RPP Contributions',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_union = fields.Monetary(
        string='Total Union Dues',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    employer_cpp = fields.Monetary(
        string='Employer CPP',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    employer_cpp2 = fields.Monetary(
        string='Employer CPP2',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    employer_ei = fields.Monetary(
        string='Employer EI',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )

    # Transmitter fields
    transmitter_bn = fields.Char(string='Business Number (BN)')
    transmitter_name = fields.Char(string='Transmitter Name')
    contact_name = fields.Char(string='Contact Name')
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')

    @api.depends('year', 'company_id')
    def _compute_name(self):
        for rec in self:
            company_name = rec.company_id.name or ''
            rec.name = 'T4 Summary - %s - %s' % (rec.year, company_name)

    @api.depends('t4_ids', 't4_ids.box_14_employment_income', 't4_ids.box_16_cpp',
                 't4_ids.box_16a_cpp2', 't4_ids.box_18_ei', 't4_ids.box_22_tax',
                 't4_ids.box_20_rpp', 't4_ids.box_44_union')
    def _compute_totals(self):
        for rec in self:
            t4s = rec.t4_ids
            rec.total_employees = len(t4s)
            rec.total_employment_income = sum(t4s.mapped('box_14_employment_income'))
            rec.total_cpp = sum(t4s.mapped('box_16_cpp'))
            rec.total_cpp2 = sum(t4s.mapped('box_16a_cpp2'))
            rec.total_ei = sum(t4s.mapped('box_18_ei'))
            rec.total_tax = sum(t4s.mapped('box_22_tax'))
            rec.total_rpp = sum(t4s.mapped('box_20_rpp'))
            rec.total_union = sum(t4s.mapped('box_44_union'))
            rec.employer_cpp = rec.total_cpp
            rec.employer_cpp2 = rec.total_cpp2
            rec.employer_ei = round(rec.total_ei * 1.4, 2)

    def action_generate_t4s(self):
        self.ensure_one()
        # Find all employees with confirmed payslips in the year for this company
        payslips = self.env['hr.payslip'].search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['done', 'paid']),
            ('date_from', '>=', '%s-01-01' % self.year),
            ('date_to', '<=', '%s-12-31' % self.year),
        ])
        employee_ids = payslips.mapped('employee_id').ids

        for employee_id in employee_ids:
            existing = self.env['hr.payroll.t4'].search([
                ('employee_id', '=', employee_id),
                ('year', '=', self.year),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if existing:
                t4 = existing
            else:
                t4 = self.env['hr.payroll.t4'].create({
                    'year': self.year,
                    'employee_id': employee_id,
                    'company_id': self.company_id.id,
                })
            t4.action_compute()
            t4.summary_id = self.id

    def action_export_xml(self):
        self.ensure_one()
        nsmap = {
            None: 'http://www.cra-arc.gc.ca/enov/ol/interfaces/efile/partnership/t4'
        }
        root = etree.Element('Submission', nsmap=nsmap)

        # T619 header
        t619 = etree.SubElement(root, 'T619')
        self._add_xml_element(t619, 'sbmt_ref_id', 'T4-%s-%s' % (self.year, self.id))
        self._add_xml_element(t619, 'rpt_tcd', 'O')
        bn = self.transmitter_bn or ''
        self._add_xml_element(t619, 'trnmtr_nbr', 'MM' + bn[:7].ljust(7, '0') if bn else 'MM0000000')
        self._add_xml_element(t619, 'trnmtr_tcd', '4')
        self._add_xml_element(t619, 'summ_cnt', '1')
        self._add_xml_element(t619, 'lang_cd', 'E')

        trnmtr_nm = etree.SubElement(t619, 'TRNMTR_NM')
        self._add_xml_element(trnmtr_nm, 'l1_nm', self.transmitter_name or self.company_id.name or '')

        company = self.company_id
        trnmtr_addr = etree.SubElement(t619, 'TRNMTR_ADDR')
        if company.street:
            self._add_xml_element(trnmtr_addr, 'addr_l1_txt', company.street)
        if company.city:
            self._add_xml_element(trnmtr_addr, 'cty_nm', company.city)
        if company.state_id:
            self._add_xml_element(trnmtr_addr, 'prov_cd', company.state_id.code)
        if company.zip:
            self._add_xml_element(trnmtr_addr, 'pstl_cd', company.zip)
        self._add_xml_element(trnmtr_addr, 'cntry_cd', 'CAN')

        if self.contact_name or self.contact_phone or self.contact_email:
            cntc = etree.SubElement(t619, 'CNTC')
            self._add_xml_element(cntc, 'cntc_nm', self.contact_name)
            if self.contact_phone:
                phone = ''.join(filter(str.isdigit, self.contact_phone))
                if len(phone) >= 10:
                    self._add_xml_element(cntc, 'cntc_area_cd', phone[:3])
                    self._add_xml_element(cntc, 'cntc_phn_nbr', phone[3:10])
            self._add_xml_element(cntc, 'cntc_email_area', self.contact_email)

        # T4Return
        t4_return = etree.SubElement(root, 'T4Return')

        # T4Summary
        t4_summary = etree.SubElement(t4_return, 'T4Summary')
        bn15 = (self.transmitter_bn or '')[:15]
        self._add_xml_element(t4_summary, 'bn', bn15)
        self._add_xml_element(t4_summary, 'tx_yr', str(self.year))
        self._add_xml_element(t4_summary, 'slp_cnt', str(self.total_employees))

        payr_nm = etree.SubElement(t4_summary, 'PAYR_NM')
        self._add_xml_element(payr_nm, 'l1_nm', company.name or '')

        payr_addr = etree.SubElement(t4_summary, 'PAYR_ADDR')
        if company.street:
            self._add_xml_element(payr_addr, 'addr_l1_txt', company.street)
        if company.city:
            self._add_xml_element(payr_addr, 'cty_nm', company.city)
        if company.state_id:
            self._add_xml_element(payr_addr, 'prov_cd', company.state_id.code)
        if company.zip:
            self._add_xml_element(payr_addr, 'pstl_cd', company.zip)
        self._add_xml_element(payr_addr, 'cntry_cd', 'CAN')

        t4_tamt = etree.SubElement(t4_summary, 'T4_TAMT')
        self._add_xml_amount(t4_tamt, 'tot_empt_incm_amt', self.total_employment_income)
        self._add_xml_amount(t4_tamt, 'tot_empe_cpp_amt', self.total_cpp)
        self._add_xml_amount(t4_tamt, 'tot_empe_eip_amt', self.total_ei)
        self._add_xml_amount(t4_tamt, 'tot_itx_ddct_amt', self.total_tax)
        self._add_xml_amount(t4_tamt, 'tot_empr_cpp_amt', self.employer_cpp)
        self._add_xml_amount(t4_tamt, 'tot_empr_eip_amt', self.employer_ei)

        # T4Slips
        for t4 in self.t4_ids:
            slip_elem = etree.SubElement(t4_return, 'T4Slip')

            emp = t4.employee_id
            empe_nm = etree.SubElement(slip_elem, 'EMPE_NM')
            name_parts = (emp.name or '').split(' ', 1)
            self._add_xml_element(empe_nm, 'snm', name_parts[-1] if len(name_parts) > 1 else emp.name or '')
            self._add_xml_element(empe_nm, 'gvn_nm', name_parts[0] if len(name_parts) > 1 else '')

            if emp.private_street or emp.private_city:
                empe_addr = etree.SubElement(slip_elem, 'EMPE_ADDR')
                if emp.private_street:
                    self._add_xml_element(empe_addr, 'addr_l1_txt', emp.private_street)
                if emp.private_city:
                    self._add_xml_element(empe_addr, 'cty_nm', emp.private_city)
                if emp.private_state_id:
                    self._add_xml_element(empe_addr, 'prov_cd', emp.private_state_id.code)
                if emp.private_zip:
                    self._add_xml_element(empe_addr, 'pstl_cd', emp.private_zip)
                self._add_xml_element(empe_addr, 'cntry_cd', 'CAN')

            self._add_xml_element(slip_elem, 'sin', t4.employee_sin or '')
            self._add_xml_element(slip_elem, 'empe_nbr', str(emp.id))
            self._add_xml_element(slip_elem, 'prov_cd', t4.province_of_employment or '')

            t4_amt = etree.SubElement(slip_elem, 'T4_AMT')
            self._add_xml_amount(t4_amt, 'empt_incm_amt', t4.box_14_employment_income)
            self._add_xml_amount(t4_amt, 'cpp_cntrb_amt', t4.box_16_cpp)
            self._add_xml_amount(t4_amt, 'empe_eip_amt', t4.box_18_ei)
            self._add_xml_amount(t4_amt, 'itx_ddct_amt', t4.box_22_tax)
            self._add_xml_amount(t4_amt, 'ei_insu_earn_amt', t4.box_24_ei_insurable)
            self._add_xml_amount(t4_amt, 'cpp_qpp_pnsn_amt', t4.box_26_pensionable)
            self._add_xml_amount(t4_amt, 'rpp_cntrb_amt', t4.box_20_rpp)
            self._add_xml_amount(t4_amt, 'unn_dues_amt', t4.box_44_union)

        xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        filename = 'T4_%s_%s.xml' % (self.year, (self.company_id.name or 'Company').replace(' ', '_'))
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

    def _add_xml_amount(self, parent, tag, amount):
        if amount:
            elem = etree.SubElement(parent, tag)
            elem.text = '%.2f' % amount

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})
