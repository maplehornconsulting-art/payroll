# Part of MHC. See LICENSE file for full copyright and licensing details.

import base64
from lxml import etree

from odoo import api, fields, models


class HrPayrollT4ASummary(models.Model):
    _name = 'hr.payroll.t4a.summary'
    _description = 'T4A Summary'
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
    t4a_ids = fields.One2many(
        'hr.payroll.t4a',
        'summary_id',
        string='T4A Slips',
    )

    # Computed totals
    total_recipients = fields.Integer(
        string='Total Recipients',
        compute='_compute_totals',
        store=True,
    )
    total_pension = fields.Monetary(
        string='Total Pension',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_lump_sum = fields.Monetary(
        string='Total Lump-Sum Payments',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_self_employed = fields.Monetary(
        string='Total Self-Employed Commissions',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_tax_deducted = fields.Monetary(
        string='Total Tax Deducted',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_annuities = fields.Monetary(
        string='Total Annuities',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_other = fields.Monetary(
        string='Total Other Income',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_fees = fields.Monetary(
        string='Total Fees for Services',
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
            rec.name = 'T4A Summary - %s - %s' % (rec.year, company_name)

    @api.depends('t4a_ids', 't4a_ids.box_016_pension', 't4a_ids.box_018_lump_sum',
                 't4a_ids.box_020_self_employed', 't4a_ids.box_022_tax_deducted',
                 't4a_ids.box_024_annuities', 't4a_ids.box_028_other', 't4a_ids.box_048_fees')
    def _compute_totals(self):
        for rec in self:
            t4as = rec.t4a_ids
            rec.total_recipients = len(t4as)
            rec.total_pension = sum(t4as.mapped('box_016_pension'))
            rec.total_lump_sum = sum(t4as.mapped('box_018_lump_sum'))
            rec.total_self_employed = sum(t4as.mapped('box_020_self_employed'))
            rec.total_tax_deducted = sum(t4as.mapped('box_022_tax_deducted'))
            rec.total_annuities = sum(t4as.mapped('box_024_annuities'))
            rec.total_other = sum(t4as.mapped('box_028_other'))
            rec.total_fees = sum(t4as.mapped('box_048_fees'))

    def action_export_xml(self):
        self.ensure_one()
        nsmap = {
            None: 'http://www.cra-arc.gc.ca/enov/ol/interfaces/efile/partnership/t4a'
        }
        root = etree.Element('Submission', nsmap=nsmap)

        # T619 header
        t619 = etree.SubElement(root, 'T619')
        self._add_xml_element(t619, 'sbmt_ref_id', 'T4A-%s-%s' % (self.year, self.id))
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

        # T4AReturn
        t4a_return = etree.SubElement(root, 'T4AReturn')

        # T4ASummary
        t4a_summary = etree.SubElement(t4a_return, 'T4ASummary')
        bn15 = (self.transmitter_bn or '')[:15]
        self._add_xml_element(t4a_summary, 'bn', bn15)
        self._add_xml_element(t4a_summary, 'tx_yr', str(self.year))
        self._add_xml_element(t4a_summary, 'slp_cnt', str(self.total_recipients))

        payr_nm = etree.SubElement(t4a_summary, 'PAYR_NM')
        self._add_xml_element(payr_nm, 'l1_nm', company.name or '')

        payr_addr = etree.SubElement(t4a_summary, 'PAYR_ADDR')
        if company.street:
            self._add_xml_element(payr_addr, 'addr_l1_txt', company.street)
        if company.city:
            self._add_xml_element(payr_addr, 'cty_nm', company.city)
        if company.state_id:
            self._add_xml_element(payr_addr, 'prov_cd', company.state_id.code)
        if company.zip:
            self._add_xml_element(payr_addr, 'pstl_cd', company.zip)
        self._add_xml_element(payr_addr, 'cntry_cd', 'CAN')

        t4a_tamt = etree.SubElement(t4a_summary, 'T4A_TAMT')
        self._add_xml_amount(t4a_tamt, 'tot_pens_spran_amt', self.total_pension)
        self._add_xml_amount(t4a_tamt, 'tot_lsp_amt', self.total_lump_sum)
        self._add_xml_amount(t4a_tamt, 'tot_self_empl_cmsn_amt', self.total_self_employed)
        self._add_xml_amount(t4a_tamt, 'tot_itx_ddct_amt', self.total_tax_deducted)
        self._add_xml_amount(t4a_tamt, 'tot_annty_amt', self.total_annuities)
        self._add_xml_amount(t4a_tamt, 'tot_othr_incm_amt', self.total_other)

        # T4ASlips
        for t4a in self.t4a_ids:
            slip_elem = etree.SubElement(t4a_return, 'T4ASlip')
            self._add_xml_element(slip_elem, 'rcpnt_nm', t4a.recipient_name or '')
            self._add_xml_element(slip_elem, 'sin', t4a.recipient_sin or '')
            self._add_xml_element(slip_elem, 'rcpnt_bn', t4a.recipient_bn or '')

            t4a_amt = etree.SubElement(slip_elem, 'T4A_AMT')
            self._add_xml_amount(t4a_amt, 'pens_spran_amt', t4a.box_016_pension)
            self._add_xml_amount(t4a_amt, 'lsp_amt', t4a.box_018_lump_sum)
            self._add_xml_amount(t4a_amt, 'self_empl_cmsn_amt', t4a.box_020_self_employed)
            self._add_xml_amount(t4a_amt, 'itx_ddct_amt', t4a.box_022_tax_deducted)
            self._add_xml_amount(t4a_amt, 'annty_amt', t4a.box_024_annuities)
            self._add_xml_amount(t4a_amt, 'othr_incm_amt', t4a.box_028_other)
            self._add_xml_amount(t4a_amt, 'fees_svc_amt', t4a.box_048_fees)

        xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        filename = 'T4A_%s_%s.xml' % (self.year, (self.company_id.name or 'Company').replace(' ', '_'))
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
