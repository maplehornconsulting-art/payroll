"""Provincial tax data — delegated to the T4127 parser.

Provincial basic personal amounts and tax brackets are extracted from the
T4127 Payroll Deductions Formulas publication (same source as federal data).
This module is kept for backwards compatibility; actual parsing happens in
``cra_feed.parsers.t4127``.
"""

from __future__ import annotations

SOURCE_URL = (
    "https://www.canada.ca/en/revenue-agency/services/forms-publications/"
    "payroll/t4127-payroll-deductions-formulas.html"
)


def parse(session=None) -> dict:
    """Return provincial data (BPA + tax brackets) sourced from T4127.

    This is a thin wrapper: ``cra_feed.scraper`` now reads provincial data
    directly from the T4127 parser result.  This function is preserved only
    so that any external code that imports it does not break.

    Returns a dict with keys:
      - provinces: dict[str, {"bpa": float, "tax_brackets": list}]
      - source_url: str
    """
    # The real provincial data comes from the T4127 parser (see scraper.py).
    # Returning an empty dict here signals to callers that they should use
    # the T4127 result instead.
    return {
        "provinces": {},
        "source_url": SOURCE_URL,
    }
