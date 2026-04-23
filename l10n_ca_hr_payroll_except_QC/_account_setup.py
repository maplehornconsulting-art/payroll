# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Accounting setup helpers for l10n_ca_hr_payroll_except_QC.

This module contains the GL account definitions and idempotent setup helpers
used both by the ``_post_init_hook`` (called by Odoo at install/upgrade time)
and by the unit tests (which import this file directly without a live Odoo
instance).

No Odoo ORM imports are made here so that the module is importable in a plain
Python / pytest environment.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GL account definitions
# ---------------------------------------------------------------------------
# Each entry: (xml_id_suffix, code, name, account_type, reconcile)
#
# Numbering follows the l10n_ca scheme:
#   2xxx — current liabilities (source deductions payable / net-pay clearing)
#   5xxx — payroll expense
#
# Accounts 5411, 5412, 5413 are created for future granular leave/OT expense
# tracking; the GROSS rule currently debits the combined 5410 account.
#
# Accounts 5440 and 2350 support an optional EHT (Employer Health Tax) rule
# that can be added to the structure for Ontario employers.

PAYROLL_ACCOUNTS = [
    # ---- Liability accounts ----
    ('account_2310', '2310', 'CRA Source Deductions Payable \u2014 Federal Income Tax', 'liability_current', True),
    ('account_2320', '2320', 'CRA Source Deductions Payable \u2014 CPP', 'liability_current', True),
    ('account_2321', '2321', 'CRA Source Deductions Payable \u2014 CPP2', 'liability_current', True),
    ('account_2330', '2330', 'CRA Source Deductions Payable \u2014 EI', 'liability_current', True),
    ('account_2340', '2340', 'Provincial Income Tax Withheld Payable', 'liability_current', True),
    ('account_2350', '2350', 'Ontario EHT Payable', 'liability_current', True),
    ('account_2360', '2360', 'RRSP Contributions Payable', 'liability_current', True),
    ('account_2370', '2370', 'Union Dues Payable', 'liability_current', True),
    ('account_2380', '2380', 'Net Pay Clearing', 'liability_current', True),
    # ---- Expense accounts ----
    ('account_5410', '5410', 'Salaries & Wages Expense', 'expense', False),
    ('account_5411', '5411', 'Paid Time Off Expense', 'expense', False),
    ('account_5412', '5412', 'Sick Time Off Expense', 'expense', False),
    ('account_5413', '5413', 'Overtime Expense', 'expense', False),
    ('account_5420', '5420', 'CPP Employer Contribution Expense', 'expense', False),
    ('account_5421', '5421', 'CPP2 Employer Contribution Expense', 'expense', False),
    ('account_5430', '5430', 'EI Employer Premium Expense', 'expense', False),
    ('account_5440', '5440', 'Ontario EHT Expense', 'expense', False),
]

SAL_JOURNAL = {
    'name': 'Salary Journal',
    'type': 'general',
    'code': 'SAL',
}

# ---------------------------------------------------------------------------
# Setup helpers (called from _post_init_hook)
# ---------------------------------------------------------------------------


def ensure_payroll_accounts(env, company):
    """Create the 17 Canadian payroll GL accounts for *company* if absent.

    Idempotent: an account is skipped when a record with the same ``code``
    already exists for that company.

    Returns a dict mapping account ``code`` → account record for every
    account that was already present or was created by this call.
    """
    Account = env['account.account']
    existing = {
        rec.code: rec
        for rec in Account.search([('company_ids', 'in', company.id)])
    }
    result = dict(existing)
    for _xml_id, code, name, account_type, reconcile in PAYROLL_ACCOUNTS:
        if code not in existing:
            vals = {
                'name': name,
                'code': code,
                'account_type': account_type,
                'company_id': company.id,
            }
            if reconcile:
                vals['reconcile'] = True
            result[code] = Account.with_company(company).create(vals)
    return result


def ensure_sal_journal(env, company):
    """Create (or return) the SAL Salary Journal for *company*.

    Idempotent: returns the existing journal when code ``SAL`` already exists
    for the company.
    """
    Journal = env['account.journal']
    journal = Journal.search([
        ('code', '=', SAL_JOURNAL['code']),
        ('company_id', '=', company.id),
    ], limit=1)
    if not journal:
        journal = Journal.with_company(company).create({
            **SAL_JOURNAL,
            'company_id': company.id,
        })
    return journal


def assign_journal_to_structures(env, journal):
    """Set *journal* on the Canadian payroll structures if they lack one.

    ``hr.payroll.structure`` gains a ``journal_id`` field when
    ``hr_payroll_account`` is installed.  We set it only when the field is
    present and the structure has no journal configured yet, so that existing
    manual overrides are preserved.
    """
    Structure = env['hr.payroll.structure']
    if 'journal_id' not in Structure._fields:
        return

    ca_xmlids = [
        'l10n_ca_hr_payroll_except_QC.hr_payroll_structure_ca_employee_salary',
        'l10n_ca_hr_payroll_except_QC.hr_payroll_structure_ca_employee_salary_salaried',
    ]
    for xmlid in ca_xmlids:
        struct = env.ref(xmlid, raise_if_not_found=False)
        if struct and not struct.journal_id:
            struct.journal_id = journal
