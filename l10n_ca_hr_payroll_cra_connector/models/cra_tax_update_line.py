# Part of MHC. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feed path → hr.rule.parameter xml id mapping
# ---------------------------------------------------------------------------
# Maps a dotted JSON path (as produced by _build_lines_from_payload) to the
# xml id of the *parent* hr.rule.parameter in l10n_ca_hr_payroll_except_QC.
# The xml id is prefixed with the module name so env.ref() can resolve it.
# Paths with no confident mapping are set to None with a # TODO comment.
# ---------------------------------------------------------------------------
_FEED_TO_RULE_PARAM = {
    # CPP
    "cpp.rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_cpp_employee_rate",
    "cpp.ympe": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_cpp_ympe",
    "cpp.basic_exemption": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_cpp_basic_exemption",
    # CPP2
    "cpp2.rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_cpp2_rate",
    "cpp2.yampe": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_cpp2_ceiling",
    # EI
    "ei.rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_ei_employee_rate",
    "ei.max_insurable_earnings": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_ei_max_insurable",
    # Federal — BPA
    "federal.bpaf.max": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_basic_personal_amount",
    "federal.bpaf.min": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_bpa_min",
    # Federal — k1_rate: same numeric value as rate_1, but semantically it is
    # the "lowest rate" constant used for non-refundable tax credits.
    # TODO: confirm whether k1_rate maps to rule_parameter_l10n_ca_fed_rate_1
    "federal.k1_rate": None,
    # Federal — tax brackets (up to 5 brackets in T4127)
    "federal.tax_brackets[0].up_to": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_bracket_1",
    "federal.tax_brackets[0].rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_rate_1",
    "federal.tax_brackets[1].up_to": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_bracket_2",
    "federal.tax_brackets[1].rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_rate_2",
    "federal.tax_brackets[2].up_to": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_bracket_3",
    "federal.tax_brackets[2].rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_rate_3",
    "federal.tax_brackets[3].up_to": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_bracket_4",
    "federal.tax_brackets[3].rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_rate_4",
    # Top bracket has no up_to threshold; only the rate applies.
    "federal.tax_brackets[4].rate": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_fed_rate_5",
    # Provincial tax config is stored as a single JSON blob parameter.
    # Individual province BPA / bracket lines map to that one parameter.
    # TODO: implement a JSON-merge strategy for the provincial config blob.
    "provinces.ON.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.BC.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.AB.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.SK.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.MB.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.NB.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.NS.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.PE.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.NL.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.NT.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.YT.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
    "provinces.NU.bpa": "l10n_ca_hr_payroll_except_QC.rule_parameter_l10n_ca_prov_tax_config",
}

# Province codes supported (no Quebec — matches base module scope)
_SUPPORTED_PROVINCES = frozenset(
    ["AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "SK", "YT"]
)


class CraTaxUpdateLine(models.Model):
    _name = "cra.tax.update.line"
    _description = "CRA Tax Update Line"
    _order = "path"

    update_id = fields.Many2one(
        "cra.tax.update",
        string="Update",
        required=True,
        ondelete="cascade",
        index=True,
    )
    path = fields.Char(
        string="Feed Path",
        required=True,
        help="Dotted JSON path in the feed payload, e.g. 'provinces.ON.bpa'.",
    )
    rule_parameter_xml_id = fields.Char(
        string="Rule Parameter XML ID",
        help=(
            "XML ID of the target hr.rule.parameter in l10n_ca_hr_payroll_except_QC. "
            "Empty if no mapping has been defined yet."
        ),
    )
    old_value = fields.Char(string="Current Value")
    new_value = fields.Char(string="New Value")
    value_type = fields.Selection(
        [("float", "Float"), ("int", "Integer"), ("json", "JSON")],
        string="Value Type",
        default="float",
    )
    selected = fields.Boolean(
        string="Apply",
        default=True,
        help="Uncheck to skip this line when applying the update.",
    )
    change_status = fields.Selection(
        [
            ("new", "New"),
            ("changed", "Changed"),
            ("unchanged", "Unchanged"),
        ],
        string="Status",
        compute="_compute_change_status",
        store=True,
    )

    @api.depends("old_value", "new_value")
    def _compute_change_status(self):
        for rec in self:
            if not rec.old_value:
                rec.change_status = "new"
            elif rec.old_value == rec.new_value:
                rec.change_status = "unchanged"
            else:
                rec.change_status = "changed"
