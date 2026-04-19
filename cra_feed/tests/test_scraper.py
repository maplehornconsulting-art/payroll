"""Unit tests for the CRA feed scraper parsers.

All tests use local fixture HTML files and mock ``requests.get`` so that no
real network calls are made.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the repo root is on the path so ``cra_feed`` is importable.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _mock_session(*url_html_pairs: tuple[str, str]) -> MagicMock:
    """
    Build a mock ``requests.Session`` whose ``.get()`` returns the supplied
    HTML strings for their respective URLs (matched by substring).
    """
    mapping = dict(url_html_pairs)

    session = MagicMock()

    def _fake_get(url: str, **kwargs):
        for key, html in mapping.items():
            if key in url:
                resp = MagicMock()
                resp.text = html
                resp.raise_for_status = MagicMock()
                return resp
        resp = MagicMock()
        resp.text = "<html><body>Not found</body></html>"
        resp.raise_for_status = MagicMock()
        return resp

    session.get.side_effect = _fake_get
    return session


# ---------------------------------------------------------------------------
# t4127 parser tests
# ---------------------------------------------------------------------------

class TestT4127FederalParsing:
    """Tests for the federal bracket, BPAF, and K1 extraction."""

    def _get_soup(self):
        from bs4 import BeautifulSoup
        return BeautifulSoup(_read_fixture("t4127_doc.html"), "lxml")

    def test_federal_brackets_count(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        brackets = result["tax_brackets"]
        assert len(brackets) == 5, f"Expected 5 brackets, got {len(brackets)}: {brackets}"

    def test_federal_bracket_rates(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        brackets = result["tax_brackets"]
        expected_rates = [0.14, 0.205, 0.26, 0.29, 0.33]
        actual_rates = [b["rate"] for b in brackets]
        assert actual_rates == pytest.approx(expected_rates, abs=1e-4), \
            f"Bracket rates mismatch: {actual_rates}"

    def test_federal_bracket_top_is_none(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        assert result["tax_brackets"][-1]["up_to"] is None, \
            "Top bracket up_to should be None"

    def test_federal_bracket_first_threshold(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        first_up_to = result["tax_brackets"][0]["up_to"]
        assert first_up_to == pytest.approx(58523.0), \
            f"First bracket upper bound should be ~58523, got {first_up_to}"

    def test_k1_rate(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        assert result["k1_rate"] == pytest.approx(0.14, abs=1e-4), \
            f"K1 rate should be 0.14, got {result['k1_rate']}"

    def test_bpaf_max(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        assert result["bpaf"]["max"] == pytest.approx(16452.0), \
            f"BPAF max should be 16452, got {result['bpaf']['max']}"

    def test_bpaf_min(self):
        from cra_feed.parsers.t4127 import _parse_federal
        soup = self._get_soup()
        result = _parse_federal(soup)
        assert result["bpaf"]["min"] == pytest.approx(14538.0), \
            f"BPAF min should be 14538, got {result['bpaf']['min']}"


class TestT4127EffectiveDate:
    """Tests for effective-date extraction."""

    def test_effective_date_from_title(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_effective_date
        html = """
        <html>
          <head><title>Payroll Deductions Formulas – Effective January 1, 2026</title></head>
          <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")
        date_str = _parse_effective_date(soup)
        assert date_str == "2026-01-01", f"Got {date_str!r}"

    def test_effective_date_from_heading(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_effective_date
        html = """
        <html>
          <head><title>T4127-JAN</title></head>
          <body>
            <h2>Effective July 1, 2025</h2>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")
        date_str = _parse_effective_date(soup)
        assert date_str == "2025-07-01", f"Got {date_str!r}"

    def test_missing_effective_date_returns_none(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_effective_date
        html = "<html><head><title>No date here</title></head><body></body></html>"
        soup = BeautifulSoup(html, "lxml")
        assert _parse_effective_date(soup) is None


class TestT4127ProvinceON:
    """Tests for Ontario provincial data extraction."""

    def _get_soup(self):
        from bs4 import BeautifulSoup
        return BeautifulSoup(_read_fixture("t4127_doc.html"), "lxml")

    def test_on_brackets_count(self):
        from cra_feed.parsers.t4127 import _parse_one_province
        soup = self._get_soup()
        result = _parse_one_province(soup, "ontario", "ON")
        assert result is not None, "Ontario province data should not be None"
        assert len(result["tax_brackets"]) == 5, \
            f"Expected 5 ON brackets, got {len(result['tax_brackets'])}"

    def test_on_bracket_rates(self):
        from cra_feed.parsers.t4127 import _parse_one_province
        soup = self._get_soup()
        result = _parse_one_province(soup, "ontario", "ON")
        actual_rates = [b["rate"] for b in result["tax_brackets"]]
        expected_rates = [0.0505, 0.0915, 0.1116, 0.1216, 0.1316]
        assert actual_rates == pytest.approx(expected_rates, abs=1e-4), \
            f"ON bracket rates mismatch: {actual_rates}"

    def test_on_top_bracket_none(self):
        from cra_feed.parsers.t4127 import _parse_one_province
        soup = self._get_soup()
        result = _parse_one_province(soup, "ontario", "ON")
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_on_bpa(self):
        from cra_feed.parsers.t4127 import _parse_one_province
        soup = self._get_soup()
        result = _parse_one_province(soup, "ontario", "ON")
        assert result["bpa"] == pytest.approx(11865.0, abs=1.0), \
            f"ON BPA should be ~11865, got {result['bpa']}"


class TestT4127EditionDiscovery:
    """Tests for the index/edition URL discovery logic."""

    def test_find_edition_url_jan(self):
        from cra_feed.parsers.t4127 import _find_edition_url
        index_html = _read_fixture("t4127_index.html")
        url = _find_edition_url(index_html)
        assert "jan" in url.lower(), f"Expected JAN in URL, got: {url}"
        assert url.endswith(".html"), f"Expected .html, got: {url}"

    def test_find_edition_url_skips_pdf(self):
        from cra_feed.parsers.t4127 import _find_edition_url
        html = """
        <html><body>
          <a href="/t4127-payroll-deductions-formulas/t4127-jan.pdf">T4127 PDF</a>
          <a href="/t4127-payroll-deductions-formulas/t4127-jan.html">T4127 HTML</a>
        </body></html>
        """
        url = _find_edition_url(html)
        assert url.endswith(".html")
        assert "jan" in url.lower()

    def test_find_document_url_follows_link(self):
        from cra_feed.parsers.t4127 import _find_document_url
        edition_html = _read_fixture("t4127_edition.html")
        doc_url = _find_document_url(
            "https://www.canada.ca/en/.../t4127-jan.html",
            edition_html,
        )
        assert "computer-programs" in doc_url, \
            f"Expected 'computer-programs' in doc URL, got: {doc_url}"

    def test_find_document_url_returns_same_if_doc_contains_data(self):
        from cra_feed.parsers.t4127 import _find_document_url
        doc_html = _read_fixture("t4127_doc.html")
        url = "https://www.canada.ca/en/.../t4127-jan-doc.html"
        result = _find_document_url(url, doc_html)
        assert result == url, "Should return same URL when page already has tax data"


# ---------------------------------------------------------------------------
# CPP / EI parser tests
# ---------------------------------------------------------------------------

class TestCppParser:
    """Tests for the CPP/CPP2 parser."""

    def test_cpp_rate_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, cpp2 = _parse_cpp_page(html)
        assert cpp["rate"] == pytest.approx(0.0595, abs=1e-5), \
            f"CPP rate should be 0.0595, got {cpp['rate']}"

    def test_cpp_ympe_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(html)
        assert cpp["ympe"] == 74600, f"YMPE should be 74600, got {cpp['ympe']}"

    def test_cpp_basic_exemption_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(html)
        assert cpp["basic_exemption"] == 3500, \
            f"Basic exemption should be 3500, got {cpp['basic_exemption']}"

    def test_cpp2_rate_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            _, cpp2 = _parse_cpp_page(html)
        assert cpp2["rate"] == pytest.approx(0.04, abs=1e-5), \
            f"CPP2 rate should be 0.04, got {cpp2['rate']}"

    def test_cpp2_yampe_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            _, cpp2 = _parse_cpp_page(html)
        assert cpp2["yampe"] == 85000, f"YAMPE should be 85000, got {cpp2['yampe']}"

    def test_cpp_missing_year_returns_empty(self):
        """If no row matches the current year, both dicts should be empty."""
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=1999):
            cpp, cpp2 = _parse_cpp_page(html)
        assert cpp == {}
        assert cpp2 == {}


class TestEiParser:
    """Tests for the EI parser."""

    def test_ei_rate_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_ei_page
        html = _read_fixture("ei_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            ei = _parse_ei_page(html)
        assert ei["rate"] == pytest.approx(0.0163, abs=1e-5), \
            f"EI rate should be 0.0163, got {ei['rate']}"

    def test_ei_max_insurable_2026(self):
        from cra_feed.parsers.cpp_ei import _parse_ei_page
        html = _read_fixture("ei_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            ei = _parse_ei_page(html)
        assert ei["max_insurable_earnings"] == 68900, \
            f"Max insurable should be 68900, got {ei['max_insurable_earnings']}"

    def test_ei_missing_year_returns_empty(self):
        from cra_feed.parsers.cpp_ei import _parse_ei_page
        html = _read_fixture("ei_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=1999):
            ei = _parse_ei_page(html)
        assert ei == {}


# ---------------------------------------------------------------------------
# Number parsing helper tests
# ---------------------------------------------------------------------------

class TestParseNum:
    def test_dollars_with_comma(self):
        from cra_feed.parsers.t4127 import _parse_num
        assert _parse_num("$71,300") == pytest.approx(71300.0)

    def test_percentage(self):
        from cra_feed.parsers.t4127 import _parse_num
        assert _parse_num("5.95%") == pytest.approx(5.95)

    def test_plain_decimal(self):
        from cra_feed.parsers.t4127 import _parse_num
        assert _parse_num("  0.1400  ") == pytest.approx(0.14)

    def test_dollar_no_comma(self):
        from cra_feed.parsers.t4127 import _parse_num
        assert _parse_num("$3500") == pytest.approx(3500.0)
