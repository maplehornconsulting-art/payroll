# Part of MHC. See LICENSE file for full copyright and licensing details.

from odoo import api, models


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
        """
        Structure = self.env["hr.payroll.structure"]
        if isinstance(source_struct, int):
            source_struct = Structure.browse(source_struct)
        if isinstance(target_struct, int):
            target_struct = Structure.browse(target_struct)

        existing_codes = {r.code for r in target_struct.rule_ids}
        for rule in source_struct.rule_ids:
            if rule.code in existing_codes:
                continue
            rule.copy({
                "struct_id": target_struct.id,
                "name": rule.name,
                "code": rule.code,
            })
