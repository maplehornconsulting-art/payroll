# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class HrPayrollStructure(models.Model):
    _inherit = "hr.payroll.structure"

    @api.model
    def _l10n_ca_clone_rules_to_salaried(self, structs):
        """Copy every salary rule from structs[0] into structs[1].

        Idempotent on rule ``code``: if the target structure already contains a
        rule with the same code, it is left unchanged.  Safe to call from a
        data file on every upgrade — re-running does not duplicate rules.

        :param structs: recordset of exactly two ``hr.payroll.structure`` records
                        where ``structs[0]`` is the source (hourly) and
                        ``structs[1]`` is the target (salaried).
        """
        source_struct = structs[0]
        target_struct = structs[1]
        existing_codes = {r.code for r in target_struct.rule_ids}
        for rule in source_struct.rule_ids:
            if rule.code in existing_codes:
                continue
            rule.copy({
                "struct_id": target_struct.id,
                "name": rule.name,
                "code": rule.code,
            })
