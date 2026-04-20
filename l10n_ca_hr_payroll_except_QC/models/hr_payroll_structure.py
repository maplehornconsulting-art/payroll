# Part of MHC. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Fields to copy from a source salary rule to the cloned salaried rule.
# Each entry is guarded at runtime with ``if fname in rule._fields`` so the
# code stays safe across Odoo 17/18/19 where field availability may vary.
_CLONE_FIELDS = (
    "sequence",
    "category_id",
    "condition_select",
    "condition_python",
    "condition_range",
    "condition_range_min",
    "condition_range_max",
    "amount_select",
    "amount_fix",
    "amount_percentage",
    "amount_percentage_base",
    "amount_python_compute",
    "appears_on_payslip",
    "active",
    "account_debit",
    "account_credit",
    "analytic_account_id",
    "note",
    "partner_id",
    "register_id",
)


class HrPayrollStructure(models.Model):
    _inherit = "hr.payroll.structure"

    @api.model
    def _l10n_ca_clone_rules_to_salaried(self, source_struct, target_struct):
        """Copy every salary rule from *source_struct* into *target_struct*.

        Idempotent on rule ``code`` — re-running an upgrade does not
        duplicate rules.

        The XML ``<function>`` tag passes the eval'd list as positional
        args, so each argument arrives as a plain integer id rather than a
        recordset. Browse them defensively to support both call styles.

        Uses an explicit field-by-field create (rather than ``rule.copy()``)
        so that fields with ``copy=False`` — in particular ``account_debit``,
        ``account_credit``, and ``analytic_account_id`` — are always
        transferred to the salaried rule, giving it full accounting
        integration.
        """
        Structure = self.env["hr.payroll.structure"]
        Rule = self.env["hr.salary.rule"]
        if isinstance(source_struct, int):
            source_struct = Structure.browse(source_struct)
        if isinstance(target_struct, int):
            target_struct = Structure.browse(target_struct)

        existing_codes = {r.code for r in target_struct.rule_ids}
        cloned = skipped = 0
        for rule in source_struct.rule_ids:
            if rule.code in existing_codes:
                skipped += 1
                continue
            vals = {}
            for fname in _CLONE_FIELDS:
                if fname not in rule._fields:
                    continue
                field = rule._fields[fname]
                value = rule[fname]
                if field.type == "many2one":
                    vals[fname] = value.id if value else False
                else:
                    vals[fname] = value
            vals.update({
                "struct_id": target_struct.id,
                "name": rule.name,
                "code": rule.code,
            })
            try:
                Rule.create(vals)
                cloned += 1
            except Exception as e:
                _logger.warning(
                    "l10n_ca clone: failed to copy rule %s to salaried structure: %s",
                    rule.code, e,
                )
        _logger.info(
            "l10n_ca clone: cloned %d rule(s), skipped %d existing on '%s'",
            cloned, skipped, target_struct.name,
        )
