# Part of MHC. See LICENSE file for full copyright and licensing details.

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CraTaxUpdateApplyWizard(models.TransientModel):
    _name = "cra.tax.update.apply.wizard"
    _description = "Apply CRA Tax Update Wizard"

    update_id = fields.Many2one(
        "cra.tax.update",
        string="CRA Tax Update",
        required=True,
        ondelete="cascade",
    )
    line_ids = fields.One2many(
        "cra.tax.update.line",
        related="update_id.line_ids",
        string="Update Lines",
    )
    confirm_disclaimer = fields.Boolean(
        string="I confirm that a qualified payroll professional has reviewed these changes",
        default=False,
        help=(
            "You must check this box to confirm that the proposed tax parameter changes "
            "have been reviewed by a qualified Canadian payroll professional and are correct "
            "before applying them to live payroll."
        ),
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        update_id = self.env.context.get("default_update_id")
        if update_id:
            res["update_id"] = update_id
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.confirm_disclaimer:
            raise UserError(
                _(
                    "You must confirm that a qualified payroll professional has reviewed "
                    "these changes before applying."
                )
            )

        update = self.update_id
        if update.state not in ("draft", "reviewed"):
            raise UserError(
                _("Only draft or reviewed updates can be applied.")
            )

        # Re-verify checksum from stored payload before writing anything
        if update.payload_json:
            try:
                payload = json.loads(update.payload_json)
            except ValueError as exc:
                raise UserError(
                    _("Stored payload JSON is corrupt. Cannot apply update.")
                ) from exc
            client = self.env["cra.feed.client"]
            client.verify_checksum(payload)

        update._do_apply(auto=False)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("CRA Tax Update Applied"),
                "message": _(
                    "Update '%(name)s' has been applied successfully."
                ) % {"name": update.name},
                "type": "success",
                "sticky": False,
            },
        }
