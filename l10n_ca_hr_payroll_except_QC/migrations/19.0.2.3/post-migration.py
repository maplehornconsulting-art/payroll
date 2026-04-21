# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Repair pass for databases upgraded from <= 19.0.2.2.

The buggy _post_init_hook in earlier versions archived the salaried twins of
BASIC, GROSS, and NET because they were missing from the whitelist. This
migration un-archives them so payslips on the Salaried structure compute
correctly again.

Idempotent: safe to re-run.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        # Fresh install — _post_init_hook handles it.
        return

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    xmlids = [
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_basic',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_gross',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_net',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_basic_salaried',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_gross_salaried',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_net_salaried',
    ]
    rule_ids = []
    for xmlid in xmlids:
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule:
            rule_ids.append(rule.id)

    if not rule_ids:
        _logger.warning(
            "l10n_ca 19.0.2.3 migration: no BASIC/GROSS/NET rules found to repair"
        )
        return

    rules = env['hr.salary.rule'].with_context(active_test=False).browse(rule_ids)
    archived = rules.filtered(lambda r: not r.active)
    if archived:
        archived.active = True
        _logger.info(
            "l10n_ca 19.0.2.3 migration: un-archived %d rule(s): %s",
            len(archived),
            sorted(set(archived.mapped('code'))),
        )
    else:
        _logger.info(
            "l10n_ca 19.0.2.3 migration: no archived BASIC/GROSS/NET rules to repair"
        )
