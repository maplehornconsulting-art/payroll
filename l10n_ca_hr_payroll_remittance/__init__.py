# Part of MHC. See LICENSE file for full copyright and licensing details.

from . import models
from . import wizard


def _post_init_hook(env):
    """Post-installation setup for l10n_ca_hr_payroll_remittance.

    For every Canadian company:
    1. Ensure the 'Receiver General for Canada' CRA partner exists.
    2. Create a default RemittanceConfig if one does not already exist.
    """
    if 'res.partner' not in env:
        return

    ResCompany = env['res.company']
    ca_companies = ResCompany.search([('country_id.code', '=', 'CA')])
    if not ca_companies:
        ca_companies = ResCompany.search([('id', '=', env.company.id)])

    cra_partner = _ensure_cra_partner(env)

    RemConfig = env['l10n.ca.remittance.config']
    for company in ca_companies:
        existing = RemConfig.search([('company_id', '=', company.id)], limit=1)
        if not existing:
            # Find a bank/cash journal for the company to use as default
            bank_journal = env['account.journal'].search([
                ('type', 'in', ['bank', 'cash']),
                ('company_id', '=', company.id),
            ], limit=1)
            RemConfig.with_company(company).create({
                'company_id': company.id,
                'cra_partner_id': cra_partner.id,
                'default_bank_journal_id': bank_journal.id if bank_journal else False,
            })


def _ensure_cra_partner(env):
    """Return (or create) the 'Receiver General for Canada' partner."""
    Partner = env['res.partner']
    cra = Partner.search([('name', '=', 'Receiver General for Canada')], limit=1)
    if not cra:
        ca_country = env.ref('base.ca', raise_if_not_found=False)
        cra = Partner.create({
            'name': 'Receiver General for Canada',
            'is_company': True,
            'supplier_rank': 1,
            'country_id': ca_country.id if ca_country else False,
            'website': 'https://www.canada.ca/en/revenue-agency.html',
            'comment': 'CRA — Receiver General for Canada. Used for payroll remittance payments.',
        })
    return cra
