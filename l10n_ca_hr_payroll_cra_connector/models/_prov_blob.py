# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Pure helper for building the consolidated provincial tax config blob.

This module intentionally has **no Odoo dependencies** so it can be imported
and unit-tested in a plain Python environment (no Odoo server needed).
"""

from __future__ import annotations

# Province codes supported (no Quebec — matches base module scope)
_SUPPORTED_PROVINCES = frozenset(
    ["AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "SK", "YT"]
)


def _build_prov_blob(provinces_data: dict) -> dict:
    """
    Build the consolidated provincial tax config blob from the feed payload.

    The returned dict matches the legacy ``l10n_ca_prov_tax_config`` format::

        {
            "ON": {
                "brackets": [[53891, 0.0505], ..., [0, 0.1316]],
                "bpa": 12989,
                "surtax": [[5818, 0.20], [7446, 0.36]]
            },
            "AB": {
                "brackets": [[61200, 0.08], ..., [0, 0.15]],
                "bpa": 22769,
                "surtax": []
            },
            ...
        }

    Encoding rules:

    - ``brackets``: ``[up_to, rate]`` pairs; the open-ended top bracket uses
      ``[0, rate]`` (not ``null``).
    - ``bpa``: ``int`` when a whole number, ``float`` otherwise.
    - ``surtax``: list of ``[threshold, rate]`` pairs; ``[]`` when absent.

    Parameters
    ----------
    provinces_data:
        The ``payload["provinces"]`` dict from the CRA feed.
    """

    def _encode_num(v):
        f = float(v)
        return int(f) if f.is_integer() else f

    blob = {}
    for code, prov in provinces_data.items():
        if code not in _SUPPORTED_PROVINCES:
            continue
        brackets = []
        for b in prov.get("tax_brackets", []):
            up_to = b.get("up_to")
            rate = float(b.get("rate", 0))
            brackets.append([0 if up_to is None else _encode_num(up_to), rate])
        blob[code] = {
            "bpa": _encode_num(prov.get("bpa", 0)),
            "brackets": brackets,
            "surtax": [
                [_encode_num(t), float(r)]
                for t, r in prov.get("surtax", [])
            ],
        }
    return blob
