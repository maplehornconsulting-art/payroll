"""Stub parser for the CRA T4127 federal payroll deductions formulas page.

Source URL:
  https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/
  t4127-payroll-deductions-formulas-computer-programs.html

TODO: Replace the hardcoded sample values below with real BeautifulSoup
extraction once the HTML structure of the T4127 page is confirmed.
"""

from __future__ import annotations

SOURCE_URL = (
    "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/"
    "payroll/t4127-payroll-deductions-formulas-computer-programs.html"
)


def parse(session=None) -> dict:
    """Return federal T4127 data.

    Returns a dict with keys:
      - bpaf: {"min": float, "max": float}  (Basic Personal Amount Federal)
      - k1_rate: float  (lowest federal tax rate, used to compute K1 credit)
      - tax_brackets: list of {"up_to": float|None, "rate": float}
      - effective_date: str  ISO date

    TODO: Use `session` (a requests.Session) to fetch SOURCE_URL and parse
    the HTML tables with BeautifulSoup/lxml instead of returning stubs.
    """

    # --- STUB VALUES (2026 federal parameters) ---
    # TODO: Extract bpaf.min and bpaf.max from the T4127 "Table 1" section.
    bpaf = {"min": 14538.00, "max": 16129.00}

    # TODO: Extract K1 rate from T4127 Chapter 1 formula.
    k1_rate = 0.15

    # TODO: Extract all five federal brackets from the T4127 tax table.
    # up_to=None means the top bracket (no ceiling).
    tax_brackets = [
        {"up_to": 57375.00, "rate": 0.15},
        {"up_to": 114750.00, "rate": 0.205},
        {"up_to": 158519.00, "rate": 0.26},
        {"up_to": 220000.00, "rate": 0.29},
        {"up_to": None, "rate": 0.33},
    ]

    effective_date = "2026-07-01"

    return {
        "bpaf": bpaf,
        "k1_rate": k1_rate,
        "tax_brackets": tax_brackets,
        "effective_date": effective_date,
        "source_url": SOURCE_URL,
    }
