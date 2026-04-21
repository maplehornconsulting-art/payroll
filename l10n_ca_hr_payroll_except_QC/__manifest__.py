# Part of MHC. See LICENSE file for full copyright and licensing details.

{
    'name': 'Canada - Payroll',
    'countries': ['ca'],
    'category': 'Human Resources/Payroll',
    'summary': 'Canadian Payroll with CPP/CPP2, EI, Federal & Provincial Tax, T4/T4A, ROE, CRA PD7A & Provincial Remittances — All Provinces Except Quebec',
    'depends': [
        'hr_payroll',
        'hr_payroll_account',
        'l10n_ca',
        'hr_work_entry_holidays',
        'hr_payroll_holidays',
    ],
    'auto_install': False,
    'version': '19.0.2.2',
    'description': """
Canada Payroll Rules.
=====================

    * Employee Details (SIN, Province of Employment, TD1 Claim Codes)
    * Employee Contracts
    * CPP/CPP2 Contributions (Employee & Employer)
    * EI Premiums (Employee & Employer)
    * Federal Income Tax (5 brackets, BPA phase-out)
    * Provincial Income Tax (All provinces/territories except Quebec)
      - Dynamic province detection from employee work address
      - Ontario surtax
      - Ontario Health Premium
    * Pre-tax deductions (RRSP, Union Dues)
    * Allowances/Deductions
    * Allow to configure Basic/Gross/Net Salary
    * Employee Payslip
    * Integrated with Leaves Management
    * T4 Slip Generation (auto-computed from payslips)
    * T4 Summary with CRA XML Export
    * T4A Slip (manual entry for pension/annuity/other income)
    * T4A Summary with CRA XML Export
    * Record of Employment (ROE) with XML Export
    * Period-aware salary rules (weekly / bi-weekly / semi-monthly / monthly / quarterly / annually)
    * Ship both Hourly and Salaried Canadian structure types out of the box.
    * Use Python-literal (not JSON) for hr.rule.parameter values; required by Odoo's safe_eval validator.
    * Integrates with hr_payroll_account — confirming a payslip posts a balanced account.move using Canadian GL conventions (2xxx liabilities, 5xxx expenses).

Remittances & Annual Reporting (v19.0.2.0+)
============================================

    * Remittance configuration per company (CRA remitter type, Business Number, WCB, EHT accounts).
    * Automatic daily cron creates draft remittance records per CRA schedule (quarterly / regular / Threshold 1 & 2).
    * Liability account aggregation from posted payslip journal entries (accounts 2310–2370).
    * Due-date computation per CRA schedule with weekend/holiday rollover.
    * Confirm + Pay workflow: draft journal entry clears liability accounts; account.payment registers the payment.
    * Annual dashboard: Owing Now, This Year's Remittances, Late Warnings, T4 reconciliation widget.
    * PD7A Remittance Voucher PDF (QWeb) with itemized breakdown and payment instructions.
    * Optional PD7A CSV export for CRA bulk upload (draft format — verify against T4127 Appendix C).
    * Quebec excluded — no QPP/QPIP/HSF/CNESST/RQ remittance types.
    * Multi-company safe — every model scoped by company_id.
    * Idempotent cron — SQL unique constraint prevents duplicate remittance records.
    """,
    'data': [
        'security/ir.model.access.csv',
        'data/hr_salary_rule_category_data.xml',
        'data/hr_payroll_structure_type_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/hr_rule_parameters_data.xml',
        'data/hr_payslip_input_type_data.xml',
        'data/account_account_data.xml',
        'data/account_journal_data.xml',
        'data/hr_salary_rule_data.xml',
        'data/res_partner_data.xml',
        'data/ir_cron_data.xml',
        'views/hr_employee_views.xml',
        'views/hr_version_views.xml',
        'views/report_payslip_templates.xml',
        'views/hr_payroll_t4_views.xml',
        'views/hr_payroll_t4a_views.xml',
        'views/hr_payroll_roe_views.xml',
        # Reports MUST load before views that reference their actions
        'report/remittance_voucher_report.xml',
        'report/remittance_voucher_template.xml',
        'views/l10n_ca_remittance_views.xml',
        'views/l10n_ca_remittance_dashboard_views.xml',
        'views/l10n_ca_remittance_config_views.xml',
        'views/l10n_ca_remittance_menus.xml',
        'wizard/l10n_ca_remittance_payment_wizard_views.xml',
    ],
    'demo': [
        'data/l10n_ca_hr_payroll_demo.xml',
    ],
    'author': 'MapleHorn Consulting Inc.',
    'website': 'https://www.maplehornconsulting.com',
    'support': 'info@maplehornconsulting.com',
    'license': 'OPL-1',
    'price': 250.89,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'post_init_hook': '_post_init_hook',
}
