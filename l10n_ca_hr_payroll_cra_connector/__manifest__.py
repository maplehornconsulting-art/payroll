# Part of MHC. See LICENSE file for full copyright and licensing details.

{
    'name': 'Canada - Payroll CRA Auto-Update Connector',
    'version': '19.0.1.1',
    'category': 'Human Resources/Payroll',
    'countries': ['ca'],
    'summary': (
        'Free auto-update connector for Canadian payroll tax values '
        '(CPP, EI, federal/provincial brackets, BPA) — admin-approved'
    ),
    'description': """
Canada Payroll — CRA Auto-Update Connector
==========================================

* Free companion module for Canada - Payroll (l10n_ca_hr_payroll_except_QC).
* Use Python-literal (not JSON) for hr.rule.parameter values; required by Odoo's safe_eval validator.

**What it does**

Fetches the MapleHorn CRA payroll tax feed (https://maplehornconsulting-art.github.io/payroll/v1/ca/latest.json)
on a daily schedule and creates a draft *CRA Tax Update* record whenever new data is detected.
A HR payroll manager then reviews the proposed changes (old vs new value for every parameter) and
clicks **Apply** to write the approved values into ``hr.rule.parameter`` records used by
``l10n_ca_hr_payroll_except_QC``.

**Human-approval gate (default)**

By default the module never writes tax values without explicit administrator approval.
An optional *Auto-Apply* toggle is available in Settings but is **off by default** and carries
a strong disclaimer. All payroll calculations must be reviewed and approved by a qualified
Canadian payroll professional before being applied to live payroll.

**Disclaimer**

This module is NOT an official product of the Canada Revenue Agency (CRA) or the Government of
Canada. Values are derived from publicly available CRA publications. No warranty of any kind is
provided. Always have a qualified payroll professional review any tax changes before applying them.
    """,
    'depends': ['l10n_ca_hr_payroll_except_QC'],
    'author': 'MapleHorn Consulting Inc.',
    'website': 'https://www.maplehornconsulting.com',
    'support': 'info@maplehornconsulting.com',
    'license': 'OPL-1',
    'images': ['static/description/banner.png'],
    'application': False,
    'auto_install': False,
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'views/cra_tax_update_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
        'wizard/cra_tax_update_apply_wizard_views.xml',
    ],
}
