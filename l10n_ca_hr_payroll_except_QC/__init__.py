# Part of MHC. See LICENSE file for full copyright and licensing details.

from . import models
from . import wizard


def _post_init_hook(env):
    """Archive default salary rules auto-added to Canadian structure.

    When hr_payroll creates a new structure, it automatically generates
    default rules (BASIC, GROSS, NET, etc.). Since this module defines
    its own custom BASIC/GROSS/NET rules, the defaults must be archived
    to avoid duplicates and conflicts.
    """
    # Try the external module's structure first (if l10n_ca_hr_payroll exists)
    ca_structure = env.ref(
        'l10n_ca_hr_payroll.hr_payroll_structure_ca_employee_salary',
        raise_if_not_found=False,
    )
    # Also target our own module's structure
    own_structure = env.ref(
        'l10n_ca_hr_payroll_except_QC.hr_payroll_structure_ca_employee_salary',
        raise_if_not_found=False,
    )

    structure_ids = []
    if ca_structure:
        structure_ids.append(ca_structure.id)
    if own_structure:
        structure_ids.append(own_structure.id)

    if not structure_ids:
        return

    # Codes of the default rules auto-created by hr_payroll core
    default_codes = [
        'BASIC', 'GROSS', 'NET',
        'ATTACH_SALARY', 'ASSIG_SALARY',
        'CHILD_SUPPORT', 'DEDUCTION', 'REIMBURSEMENT',
    ]

    # Find default rules that are NOT our custom ones (by XML ID)
    own_rule_xmlids = [
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_basic',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_gross',
        'l10n_ca_hr_payroll_except_QC.salary_rule_ca_net',
    ]
    own_rule_ids = set()
    for xmlid in own_rule_xmlids:
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule:
            own_rule_ids.add(rule.id)

    default_rules = env['hr.salary.rule'].search([
        ('struct_id', 'in', structure_ids),
        ('code', 'in', default_codes),
    ])

    # Archive only the auto-generated defaults, not our custom rules
    rules_to_archive = default_rules.filtered(lambda r: r.id not in own_rule_ids)
    if rules_to_archive:
        rules_to_archive.active = False
