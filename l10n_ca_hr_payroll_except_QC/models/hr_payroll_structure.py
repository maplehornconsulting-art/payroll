# Part of MHC. See LICENSE file for full copyright and licensing details.

import logging
import traceback

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

# Fields to fill in on an existing target rule when the field is blank.
# Used by the repair pass to fix databases where the old rule.copy() clone
# left accounting and compute fields empty.
_REPAIR_FIELDS = (
    "account_debit",
    "account_credit",
    "analytic_account_id",
    "amount_python_compute",
    "condition_python",
    "condition_select",
    "amount_select",
    "category_id",
    "sequence",
    "appears_on_payslip",
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
        failed_codes: list[str] = []
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
            # Validate many2one fields to prevent silent drops caused by
            # dangling references (e.g. category_id pointing to a deleted
            # record) that would raise inside Rule.create() and get swallowed.
            for fname in ('category_id', 'parent_rule_id'):
                if not vals.get(fname):
                    continue
                if fname not in rule._fields:
                    continue
                comodel = rule._fields[fname].comodel_name
                if not self.env[comodel].browse(vals[fname]).exists():
                    _logger.warning(
                        "l10n_ca clone: rule %s has dangling %s=%s — clearing it",
                        rule.code, fname, vals[fname],
                    )
                    vals[fname] = False
            try:
                Rule.create(vals)
                cloned += 1
            except Exception as e:
                _logger.error(
                    "l10n_ca clone: FAILED to copy rule %s to salaried structure '%s'.\n"
                    "  Exception: %s\n"
                    "  vals (summary): %s\n"
                    "  traceback:\n%s",
                    rule.code, target_struct.name, e,
                    {k: v for k, v in vals.items()
                     if k not in ('amount_python_compute', 'condition_python')},
                    traceback.format_exc(),
                )
                failed_codes.append(rule.code)
        # Repair pass: fill blank fields on existing target rules from the source.
        # This fixes databases where the old rule.copy()-based clone left
        # account_debit / account_credit and python compute fields blank.
        # Only fills fields that are currently falsy — intentional customisations
        # already present on the target rule are never overwritten.
        target_by_code = {r.code: r for r in target_struct.rule_ids}
        repaired = unchanged = 0
        for src_rule in source_struct.rule_ids:
            tgt_rule = target_by_code.get(src_rule.code)
            if not tgt_rule:
                continue  # newly created above — no repair needed
            patch = {}
            for fname in _REPAIR_FIELDS:
                if fname not in src_rule._fields or fname not in tgt_rule._fields:
                    continue
                src_val = src_rule[fname]
                tgt_val = tgt_rule[fname]
                field = src_rule._fields[fname]
                if field.type == "many2one":
                    if not tgt_val and src_val:
                        patch[fname] = src_val.id
                else:
                    # Treat None / "" / 0 as missing for repair purposes.
                    if not tgt_val and src_val:
                        patch[fname] = src_val
            if patch:
                try:
                    tgt_rule.write(patch)
                    repaired += 1
                    _logger.info(
                        "l10n_ca clone: repaired rule %s on '%s' with fields %s",
                        src_rule.code, target_struct.name, list(patch.keys()),
                    )
                except Exception as e:
                    _logger.error(
                        "l10n_ca clone: failed to repair rule %s on '%s': %s",
                        src_rule.code, target_struct.name, e,
                    )
            else:
                unchanged += 1

        _logger.info(
            "l10n_ca clone: cloned %d new, repaired %d existing, skipped %d unchanged"
            "%s on '%s'",
            cloned, repaired, unchanged,
            f", FAILED {len(failed_codes)}: {sorted(failed_codes)}" if failed_codes else "",
            target_struct.name,
        )

        # Final-state assertion: log an ERROR if the target is missing any source rules.
        source_codes = {r.code for r in source_struct.rule_ids}
        target_codes = {r.code for r in target_struct.rule_ids}
        missing = source_codes - target_codes
        if missing:
            _logger.error(
                "l10n_ca clone: salaried structure '%s' is missing %d rule(s) "
                "that exist on the hourly structure: %s.  "
                "Run `-u l10n_ca_hr_payroll_except_QC` to re-trigger the clone.",
                target_struct.name, len(missing), sorted(missing),
            )

    def _register_hook(self):
        """Server-startup self-check: verify Hourly and Salaried structures are in sync.

        Called by Odoo's module registry at server start.  Logs an INFO line
        with rule counts, then an ERROR (visible in the server log without
        raising an exception) if the Salaried structure is missing rules that
        exist on the Hourly structure.  When missing rules are found **and**
        the registry is fully ready, the clone/repair pass is re-run
        automatically to self-heal the database.
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
            if not hourly or not salaried:
                return res

            hourly_codes   = {r.code for r in hourly.rule_ids}
            salaried_codes = {r.code for r in salaried.rule_ids}
            missing = hourly_codes - salaried_codes

            _logger.info(
                "l10n_ca: Hourly structure has %d rules, Salaried structure has %d rules",
                len(hourly_codes), len(salaried_codes),
            )

            if missing:
                _logger.error(
                    "l10n_ca startup check: Salaried structure is missing %d rule(s) "
                    "present on the Hourly structure: %s.  "
                    "Attempting auto-heal via clone/repair pass.",
                    len(missing), sorted(missing),
                )
                # Auto-heal: re-run the clone+repair pass so that running
                # `-u l10n_ca_hr_payroll_except_QC` (or any server restart
                # after the module upgrade) fully restores missing rules.
                if self.env.registry.ready:
                    self._l10n_ca_clone_rules_to_salaried(hourly, salaried)
            else:
                _logger.debug(
                    "l10n_ca startup check: Hourly and Salaried structures are in sync "
                    "(%d rules each).", len(hourly_codes),
                )
        except Exception as exc:
            _logger.warning(
                "l10n_ca startup check: could not compare structure rules: %s", exc,
            )
        return res
