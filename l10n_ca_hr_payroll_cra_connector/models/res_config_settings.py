# Part of MHC. See LICENSE file for full copyright and licensing details.

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cra_feed_url = fields.Char(
        string="CRA Feed URL",
        config_parameter="l10n_ca_hr_payroll_cra_connector.feed_url",
        help=(
            "URL of the CRA payroll tax JSON feed. "
            "Defaults to: https://maplehornconsulting-art.github.io/payroll/v1/ca/latest.json"
        ),
    )
    cra_feed_gpg_fingerprint = fields.Char(
        string="GPG Key Fingerprint",
        config_parameter="l10n_ca_hr_payroll_cra_connector.feed_gpg_fingerprint",
        help=(
            "Optional: fingerprint of the GPG key used to sign the feed. "
            "Requires python-gnupg to be installed. Leave empty to skip signature verification."
        ),
    )
    cra_feed_auto_apply = fields.Boolean(
        string="Auto-Apply Updates",
        config_parameter="l10n_ca_hr_payroll_cra_connector.auto_apply",
        default=False,
        help=(
            "⚠ RISK: When enabled, the cron job will automatically apply CRA tax updates "
            "without human review, provided the feed signature verifies AND every update line "
            "has a mapped hr.rule.parameter. "
            "This is OFF by default. "
            "A qualified Canadian payroll professional must review all tax changes "
            "before they are applied to live payroll. Enabling auto-apply removes that gate. "
            "MapleHorn Consulting Inc. accepts no liability for payroll errors caused by "
            "auto-applied updates."
        ),
    )
