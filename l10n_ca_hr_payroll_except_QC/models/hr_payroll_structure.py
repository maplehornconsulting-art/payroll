# Part of MHC. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class HrPayrollStructure(models.Model):
    _inherit = "hr.payroll.structure"

    def _register_hook(self):
        """Server-startup diagnostic: log a comparison of rule counts on the two
        Canadian payroll structures.

        Purely informational — never mutates data.  If a future PR declares a
        new rule on the Hourly structure but forgets the parallel Salaried
        record, this will surface the discrepancy in the server log.
        """
        res = super()._register_hook()
        try:
            hourly = self.env.ref(
                'l10n_ca_hr_payroll_except_QC.hr_payroll_structure_ca_employee_salary',
                raise_if_not_found=False,
            )
            salaried = self.env.ref(
                'l10n_ca_hr_payroll_except_QC.'
                'hr_payroll_structure_ca_employee_salary_salaried',
                raise_if_not_found=False,
            )
            if hourly and salaried:
                h_codes = {r.code for r in hourly.rule_ids}
                s_codes = {r.code for r in salaried.rule_ids}
                _logger.info(
                    "l10n_ca: Hourly structure has %d rules, Salaried structure has %d rules",
                    len(h_codes), len(s_codes),
                )
                if h_codes != s_codes:
                    _logger.error(
                        "l10n_ca: Structure rule codes differ! Only on Hourly: %s | Only on Salaried: %s",
                        sorted(h_codes - s_codes), sorted(s_codes - h_codes),
                    )
        except Exception as e:
            _logger.warning("l10n_ca: rule-count diagnostic failed: %s", e)
        return res
