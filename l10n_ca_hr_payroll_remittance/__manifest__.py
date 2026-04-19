# Part of MHC. See LICENSE file for full copyright and licensing details.

{
    'name': 'Canada - Payroll Remittance',
    'countries': ['ca'],
    'category': 'Human Resources/Payroll',
    'summary': 'Canadian Payroll Remittance Workflow — CRA PD7A, Provincial EHT, WCB, RRSP, Union Dues, Garnishments',
    'depends': [
        'l10n_ca_hr_payroll_except_QC',
        'account',
        'hr_payroll_account',
    ],
    'auto_install': False,
    'version': '19.0.1.0',
    'description': """
Canada Payroll Remittance Workflow.
=====================================

Turns Odoo into an end-to-end Canadian payroll-compliance system:

    * Remittance configuration per company (remitter type, CRA BN, WCB, EHT)
    * Automatic remittance period generation (daily cron)
    * Liability account aggregation from posted payslip journal entries
    * Due-date computation per CRA schedule (quarterly / regular / Threshold 1 & 2)
    * Confirm + Pay workflow with account.move and account.payment
    * Annual dashboard: owing now, year-to-date, late warnings, T4 reconciliation
    * Print PD7A Remittance Voucher (QWeb PDF)
    * Export PD7A file (CSV) for CRA bulk upload
    * Quebec excluded — for Rest-of-Canada only
    """,
    'data': [
        'security/ir.model.access.csv',
        'security/l10n_ca_remittance_rules.xml',
        'data/res_partner_data.xml',
        'data/ir_cron_data.xml',
        'views/l10n_ca_remittance_config_views.xml',
        'views/l10n_ca_remittance_views.xml',
        'views/l10n_ca_remittance_payment_wizard_views.xml',
        'views/l10n_ca_remittance_menus.xml',
        'report/l10n_ca_remittance_report.xml',
        'report/l10n_ca_remittance_report_templates.xml',
    ],
    'author': 'MapleHorn Consulting Inc.',
    'website': 'https://www.maplehornconsulting.com',
    'support': 'info@maplehornconsulting.com',
    'license': 'OPL-1',
    'images': ['static/description/banner.png'],
    'post_init_hook': '_post_init_hook',
}
