# Part of MHC. See LICENSE file for full copyright and licensing details.

import hashlib
import json
import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_MODULE_VERSION = "19.0.1.0"
_DEFAULT_FEED_URL = (
    "https://maplehornconsulting-art.github.io/payroll/v1/ca/latest.json"
)
_REQUEST_TIMEOUT = 30  # seconds


class CraFeedClient(models.AbstractModel):
    """Lightweight HTTP client for the MapleHorn CRA payroll tax feed.

    Isolated in its own model so HTTP calls can be mocked in tests.
    """

    _name = "cra.feed.client"
    _description = "CRA Feed Client"

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _get_param(self, key, default=""):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(key, default=default)
        )

    def _feed_url(self):
        return (
            self._get_param("l10n_ca_hr_payroll_cra_connector.feed_url")
            or _DEFAULT_FEED_URL
        )

    def _signature_url(self):
        sig_url = self._get_param(
            "l10n_ca_hr_payroll_cra_connector.feed_signature_url"
        )
        if not sig_url:
            sig_url = self._feed_url() + ".sig"
        return sig_url

    def _gpg_fingerprint(self):
        return self._get_param(
            "l10n_ca_hr_payroll_cra_connector.feed_gpg_fingerprint"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> dict:
        """Perform an HTTP GET on the configured feed URL.

        Returns the parsed JSON dict.
        Raises :exc:`odoo.exceptions.UserError` on any HTTP/network error.
        """
        url = self._feed_url()
        headers = {
            "User-Agent": (
                f"l10n_ca_hr_payroll_cra_connector/{_MODULE_VERSION} (Odoo)"
            )
        }
        _logger.info("CRA feed client: fetching %s", url)
        try:
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise UserError(
                _("CRA feed request timed out after %(timeout)s seconds: %(url)s")
                % {"timeout": _REQUEST_TIMEOUT, "url": url}
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise UserError(
                _("CRA feed HTTP error %(status)s: %(url)s")
                % {"status": exc.response.status_code, "url": url}
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise UserError(
                _("CRA feed network error: %(error)s") % {"error": str(exc)}
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise UserError(
                _("CRA feed returned invalid JSON from %(url)s") % {"url": url}
            ) from exc
        return payload

    def verify_checksum(self, payload: dict) -> bool:
        """Verify the ``checksum_sha256`` field embedded in *payload*.

        Re-computes the canonical checksum using the same algorithm as
        ``cra_feed/scraper.py``:

        1. Copy the payload dict and set ``checksum_sha256`` to ``""``.
        2. Serialize with ``json.dumps(..., sort_keys=True, separators=(",", ":"))``
        3. SHA-256 hex-digest the UTF-8 bytes.

        Raises :exc:`odoo.exceptions.UserError` if the checksum does not match.
        Returns ``True`` if the checksum matches.
        """
        claimed = payload.get("checksum_sha256", "")
        canonical_payload = {**payload, "checksum_sha256": ""}
        canonical_json = json.dumps(
            canonical_payload, sort_keys=True, separators=(",", ":")
        )
        computed = hashlib.sha256(canonical_json.encode()).hexdigest()
        if computed != claimed:
            raise UserError(
                _(
                    "CRA feed checksum mismatch. "
                    "Claimed: %(claimed)s  Computed: %(computed)s. "
                    "The feed may have been tampered with or is corrupt."
                )
                % {"claimed": claimed, "computed": computed}
            )
        _logger.debug("CRA feed checksum OK: %s", computed)
        return True

    def verify_signature(self, payload_bytes: bytes, signature_bytes: bytes) -> bool:
        """Verify a GPG detached signature over *payload_bytes*.

        Returns ``True`` immediately if no GPG fingerprint is configured.

        Otherwise attempts GPG verification via the optional ``gnupg`` library.
        If the library is not installed a warning is logged and ``True`` is
        returned so the rest of the workflow is not blocked.

        .. TODO:: Implement full GPG verification once ``python-gnupg`` is
                  declared as an optional system dependency.
        """
        fingerprint = self._gpg_fingerprint()
        if not fingerprint:
            _logger.debug(
                "CRA feed: no GPG fingerprint configured — skipping signature verification."
            )
            return True
        try:
            import gnupg  # noqa: F401  # optional import
        except ImportError:
            _logger.warning(
                "CRA feed: python-gnupg is not installed — "
                "skipping GPG signature verification. "
                "Install it to enable this feature."
            )
            return True
        # TODO: implement actual GPG verification using the gnupg library.
        _logger.warning(
            "CRA feed: GPG verification stub called — "
            "signature NOT verified. Implement full verification."
        )
        return True
