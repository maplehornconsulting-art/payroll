"""Stub parser for CRA CPP and EI rates.

Source URLs (examples — actual page paths may vary):
  https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/
  payroll/payroll-deductions-contributions/canada-pension-plan-cpp/
  cpp-contribution-rates-maximums-exemptions.html

  https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/
  payroll/payroll-deductions-contributions/employment-insurance-ei/
  ei-premium-rates-maximums.html

TODO: Replace hardcoded values with real BeautifulSoup extraction.
"""

from __future__ import annotations

CPP_SOURCE_URL = (
    "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/"
    "payroll/payroll-deductions-contributions/canada-pension-plan-cpp/"
    "cpp-contribution-rates-maximums-exemptions.html"
)

EI_SOURCE_URL = (
    "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/"
    "payroll/payroll-deductions-contributions/employment-insurance-ei/"
    "ei-premium-rates-maximums.html"
)


def parse(session=None) -> dict:
    """Return CPP and EI rate data.

    Returns a dict with keys:
      - cpp:  {"rate": float, "ympe": float, "basic_exemption": float}
      - cpp2: {"rate": float, "yampe": float}
      - ei:   {"rate": float, "max_insurable_earnings": float}
      - source_urls: list[str]

    TODO: Use `session` to fetch CPP_SOURCE_URL and EI_SOURCE_URL and
    extract values from the HTML rate tables with BeautifulSoup.
    """

    # --- STUB VALUES (2026 rates) ---
    # TODO: Extract CPP employee contribution rate, YMPE, and basic exemption.
    cpp = {
        "rate": 0.0595,
        "ympe": 71300.0,
        "basic_exemption": 3500.0,
    }

    # TODO: Extract CPP2 rate and YAMPE (Year's Additional Maximum Pensionable Earnings).
    cpp2 = {
        "rate": 0.04,
        "yampe": 81900.0,
    }

    # TODO: Extract EI employee premium rate and maximum insurable earnings.
    ei = {
        "rate": 0.0166,
        "max_insurable_earnings": 65700.0,
    }

    return {
        "cpp": cpp,
        "cpp2": cpp2,
        "ei": ei,
        "source_urls": [CPP_SOURCE_URL, EI_SOURCE_URL],
    }
