"""Stub parser for CRA TD1 federal and provincial basic personal amounts.

Scope: federal + all provinces/territories EXCEPT Quebec.

Source: TD1 personal tax credits return forms published on canada.ca.
  https://www.canada.ca/en/revenue-agency/services/forms-publications/
  td1-personal-tax-credits-returns.html

TODO: Replace hardcoded values with real BeautifulSoup/PDF extraction.
"""

from __future__ import annotations

SOURCE_URL = (
    "https://www.canada.ca/en/revenue-agency/services/forms-publications/"
    "td1-personal-tax-credits-returns.html"
)

# Province/territory codes in scope (all except QC).
PROVINCES_IN_SCOPE = [
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "SK", "YT",
]


def parse(session=None) -> dict:
    """Return TD1 basic personal amounts and tax brackets by province.

    Returns a dict with keys:
      - provinces: dict[str, {"bpa": float, "tax_brackets": list}]
      - source_url: str

    TODO: For each province, fetch its TD1 form (PDF or HTML) and extract
    the basic personal amount using pdfplumber or requests + BeautifulSoup.
    Provincial tax brackets come from each province's revenue authority pages.
    """

    # --- STUB VALUES (approximate 2026 figures) ---
    # TODO: Replace each BPA with values scraped from the respective TD1 form.
    # TODO: Add real provincial tax brackets; these single-bracket stubs are
    #       placeholders only.
    provinces: dict[str, dict] = {
        "AB": {
            "bpa": 21003.0,
            "tax_brackets": [
                {"up_to": 148269.0, "rate": 0.10},
                {"up_to": 177922.0, "rate": 0.12},
                {"up_to": 237230.0, "rate": 0.13},
                {"up_to": 355845.0, "rate": 0.14},
                {"up_to": None,     "rate": 0.15},
            ],
        },
        "BC": {
            "bpa": 11981.0,
            "tax_brackets": [
                {"up_to": 45654.0,  "rate": 0.0506},
                {"up_to": 91310.0,  "rate": 0.077},
                {"up_to": 104835.0, "rate": 0.105},
                {"up_to": 127299.0, "rate": 0.1229},
                {"up_to": 172602.0, "rate": 0.147},
                {"up_to": 240716.0, "rate": 0.168},
                {"up_to": None,     "rate": 0.205},
            ],
        },
        "MB": {
            "bpa": 15780.0,
            "tax_brackets": [
                {"up_to": 47000.0, "rate": 0.108},
                {"up_to": 100000.0, "rate": 0.1275},
                {"up_to": None,    "rate": 0.174},
            ],
        },
        "NB": {
            "bpa": 12458.0,
            "tax_brackets": [
                {"up_to": 49958.0,  "rate": 0.094},
                {"up_to": 99916.0,  "rate": 0.14},
                {"up_to": 185064.0, "rate": 0.16},
                {"up_to": None,     "rate": 0.195},
            ],
        },
        "NL": {
            "bpa": 10818.0,
            "tax_brackets": [
                {"up_to": 43198.0,  "rate": 0.087},
                {"up_to": 86395.0,  "rate": 0.145},
                {"up_to": 154244.0, "rate": 0.158},
                {"up_to": 215943.0, "rate": 0.178},
                {"up_to": 275870.0, "rate": 0.198},
                {"up_to": None,     "rate": 0.213},
            ],
        },
        "NS": {
            "bpa": 8481.0,
            "tax_brackets": [
                {"up_to": 29590.0,  "rate": 0.0879},
                {"up_to": 59180.0,  "rate": 0.1495},
                {"up_to": 93000.0,  "rate": 0.1667},
                {"up_to": 150000.0, "rate": 0.175},
                {"up_to": None,     "rate": 0.21},
            ],
        },
        "NT": {
            "bpa": 16593.0,
            "tax_brackets": [
                {"up_to": 50597.0,  "rate": 0.059},
                {"up_to": 101198.0, "rate": 0.086},
                {"up_to": 164525.0, "rate": 0.122},
                {"up_to": None,     "rate": 0.1405},
            ],
        },
        "NU": {
            "bpa": 17925.0,
            "tax_brackets": [
                {"up_to": 53268.0,  "rate": 0.04},
                {"up_to": 106537.0, "rate": 0.07},
                {"up_to": 173205.0, "rate": 0.09},
                {"up_to": None,     "rate": 0.115},
            ],
        },
        "ON": {
            "bpa": 11865.0,
            "tax_brackets": [
                {"up_to": 51446.0,  "rate": 0.0505},
                {"up_to": 102894.0, "rate": 0.0915},
                {"up_to": 150000.0, "rate": 0.1116},
                {"up_to": 220000.0, "rate": 0.1216},
                {"up_to": None,     "rate": 0.1316},
            ],
        },
        "PE": {
            "bpa": 12000.0,
            "tax_brackets": [
                {"up_to": 32656.0,  "rate": 0.096},
                {"up_to": 64313.0,  "rate": 0.1337},
                {"up_to": 105000.0, "rate": 0.167},
                {"up_to": 140000.0, "rate": 0.18},
                {"up_to": None,     "rate": 0.187},
            ],
        },
        "SK": {
            "bpa": 17661.0,
            "tax_brackets": [
                {"up_to": 49720.0,  "rate": 0.105},
                {"up_to": 142058.0, "rate": 0.125},
                {"up_to": None,     "rate": 0.145},
            ],
        },
        "YT": {
            "bpa": 16129.0,
            "tax_brackets": [
                {"up_to": 57375.0,  "rate": 0.064},
                {"up_to": 114750.0, "rate": 0.09},
                {"up_to": 158519.0, "rate": 0.109},
                {"up_to": 500000.0, "rate": 0.128},
                {"up_to": None,     "rate": 0.15},
            ],
        },
    }

    return {
        "provinces": provinces,
        "source_url": SOURCE_URL,
    }
