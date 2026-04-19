"""Real parser for CRA CPP and EI rates pages.

Source URLs:
  https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/
  payroll/payroll-deductions-contributions/canada-pension-plan-cpp/
  cpp-contribution-rates-maximums-exemptions.html

  https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/
  payroll/payroll-deductions-contributions/employment-insurance-ei/
  ei-premium-rates-maximums.html
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

import requests as _requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_num(s: str) -> float:
    """Strip $, commas, % and return float."""
    return float(s.strip().replace(",", "").replace("$", "").replace("%", "").strip())


def _fetch(session, url: str) -> str:
    logger.info("Fetching %s", url)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    time.sleep(1)
    return resp.text


def _current_year() -> int:
    return date.today().year


# ---------------------------------------------------------------------------
# CPP parser
# ---------------------------------------------------------------------------

def _col_index(headers: list[str], *keywords: str) -> int | None:
    """Return the index of the first header that contains all given keywords."""
    for i, h in enumerate(headers):
        h_l = h.lower()
        if all(kw.lower() in h_l for kw in keywords):
            return i
    return None


def _cell_float(tds: list, col: int | None) -> float | None:
    """Return a float from ``tds[col]``, or ``None`` if col is out of range."""
    if col is None or col >= len(tds):
        return None
    try:
        return _parse_num(tds[col].get_text(strip=True))
    except ValueError:
        return None


def _row_year(tds: list, year_col: int | None) -> int | None:
    """Extract the 4-digit year from the year column of a data row."""
    if year_col is None or year_col >= len(tds):
        return None
    m = re.search(r"\d{4}", tds[year_col].get_text(strip=True))
    return int(m.group()) if m else None


def _extract_headers_and_data(table) -> tuple[list[str], list]:
    """Split table rows into header texts and data rows (td-only rows)."""
    header_texts: list[str] = []
    data_rows: list = []
    for row in table.find_all("tr"):
        ths = row.find_all("th")
        tds = row.find_all("td")
        if ths and not tds:
            header_texts = [th.get_text(" ", strip=True) for th in ths]
        elif tds:
            data_rows.append(tds)
    return header_texts, data_rows


def _parse_cpp_page(html: str) -> tuple[dict, dict]:
    """
    Parse CPP and CPP2 data from the CRA CPP rates page.

    Returns (cpp_dict, cpp2_dict) for the current/most-recent year.
    """
    soup = BeautifulSoup(html, "lxml")
    year = _current_year()

    cpp: dict = {}
    cpp2: dict = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_texts, data_rows = _extract_headers_and_data(table)
        if not header_texts or not data_rows:
            continue

        h_lower = [h.lower() for h in header_texts]

        # Identify which kind of table this is
        has_year_col = any("year" in h for h in h_lower)
        has_ympe = any("ympe" in h or "maximum pensionable" in h for h in h_lower)
        has_yampe = any("yampe" in h or "additional maximum" in h for h in h_lower)
        has_rate = any("rate" in h or "contribution" in h for h in h_lower)

        if not has_year_col:
            continue

        year_col = _col_index(h_lower, "year")

        if has_ympe and has_rate and not has_yampe:
            # CPP1 table
            ympe_col = _col_index(h_lower, "ympe") or _col_index(h_lower, "maximum pensionable")
            rate_col = _col_index(h_lower, "rate") or _col_index(h_lower, "contribution rate")
            exemption_col = _col_index(h_lower, "exemption")

            for tds in data_rows:
                if _row_year(tds, year_col) != year:
                    continue
                try:
                    ympe_v = _cell_float(tds, ympe_col)
                    rate_v = _cell_float(tds, rate_col)
                    if rate_v is not None and rate_v > 1:
                        rate_v /= 100.0
                    exemption_v = _cell_float(tds, exemption_col) or 3500.0
                    if ympe_v is not None and rate_v is not None:
                        cpp = {
                            "rate": rate_v,
                            "ympe": int(ympe_v),
                            "basic_exemption": int(exemption_v),
                        }
                except (ValueError, IndexError):
                    continue

        elif has_yampe or (has_ympe and has_rate and "second" in " ".join(h_lower)):
            # CPP2 table (or combined table with YAMPE column)
            yampe_col = _col_index(h_lower, "yampe") or _col_index(h_lower, "additional maximum")
            rate_col = _col_index(h_lower, "rate") or _col_index(h_lower, "contribution rate")

            for tds in data_rows:
                if _row_year(tds, year_col) != year:
                    continue
                try:
                    yampe_v = _cell_float(tds, yampe_col)
                    rate_v = _cell_float(tds, rate_col)
                    if rate_v is not None and rate_v > 1:
                        rate_v /= 100.0
                    if yampe_v is not None and rate_v is not None:
                        cpp2 = {"rate": rate_v, "yampe": int(yampe_v)}
                except (ValueError, IndexError):
                    continue

    return cpp, cpp2


# ---------------------------------------------------------------------------
# EI parser
# ---------------------------------------------------------------------------

def _parse_ei_page(html: str) -> dict:
    """
    Parse EI data from the CRA EI premium rates page.

    Returns ei_dict for the current/most-recent year.
    """
    soup = BeautifulSoup(html, "lxml")
    year = _current_year()
    ei: dict = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_texts, data_rows = _extract_headers_and_data(table)
        if not header_texts or not data_rows:
            continue

        h_lower = [h.lower() for h in header_texts]
        has_year = any("year" in h for h in h_lower)
        has_insurable = any("insurable" in h for h in h_lower)

        if not (has_year and has_insurable):
            continue

        year_col = _col_index(h_lower, "year")
        insurable_col = (
            _col_index(h_lower, "maximum annual insurable")
            or _col_index(h_lower, "insurable")
        )
        rate_col = (
            _col_index(h_lower, "employee", "rate")
            or _col_index(h_lower, "employee", "premium")
            or _col_index(h_lower, "premium rate")
            or _col_index(h_lower, "rate")
        )

        for tds in data_rows:
            if _row_year(tds, year_col) != year:
                continue
            try:
                max_ins = _cell_float(tds, insurable_col)
                rate_v = _cell_float(tds, rate_col)
                # EI rate is typically expressed as "$X.XX per $100" or as a
                # percentage; values > 1 need dividing by 100
                if rate_v is not None and rate_v > 1:
                    rate_v /= 100.0
                if max_ins is not None and rate_v is not None:
                    ei = {
                        "rate": rate_v,
                        "max_insurable_earnings": int(max_ins),
                    }
            except (ValueError, IndexError):
                continue

    return ei


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(session=None) -> dict:
    """
    Fetch and parse CRA CPP and EI rate data.

    Returns a dict with keys:
      - cpp:  {"rate": float, "ympe": int, "basic_exemption": int}
      - cpp2: {"rate": float, "yampe": int}
      - ei:   {"rate": float, "max_insurable_earnings": int}
      - source_urls: list[str]
    """
    if session is None:
        session = _requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "MapleHorn CRA Feed Scraper / contact@maplehornconsulting.com"
                )
            }
        )

    cpp_html = _fetch(session, CPP_SOURCE_URL)
    cpp, cpp2 = _parse_cpp_page(cpp_html)

    ei_html = _fetch(session, EI_SOURCE_URL)
    ei = _parse_ei_page(ei_html)

    if not cpp:
        raise ValueError(
            f"Could not parse CPP data for year {_current_year()} from {CPP_SOURCE_URL}"
        )
    if not ei:
        raise ValueError(
            f"Could not parse EI data for year {_current_year()} from {EI_SOURCE_URL}"
        )
    if not cpp2:
        logger.warning("CPP2 data not found; using zeros as placeholder")
        cpp2 = {"rate": 0.0, "yampe": 0}

    return {
        "cpp": cpp,
        "cpp2": cpp2,
        "ei": ei,
        "source_urls": [CPP_SOURCE_URL, EI_SOURCE_URL],
    }
