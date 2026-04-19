"""Unit tests for the CRA feed scraper parsers.

All tests use local fixture HTML files and mock ``requests.get`` so that no
real network calls are made.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


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
# CPP2 fallback test
# ---------------------------------------------------------------------------

class TestCppFallback:
    """Tests for CPP2 fallback when data is missing."""

    def test_cpp2_fallback_when_no_cpp2_table(self):
        """parse() should warn and return zeros when CPP2 data is absent."""
        import logging
        from unittest.mock import MagicMock
        from cra_feed.parsers import cpp_ei

        # Build a session that returns CPP HTML for CPP URL,
        # and EI HTML for EI URL.
        cpp_html = _read_fixture("cpp_page.html")
        ei_html = _read_fixture("ei_page.html")

        # HTML with no CPP2 table — strip the CPP2 table from the fixture
        cpp_html_no_cpp2 = cpp_html.replace(
            "CPP2", "IGNORED"
        ).replace("yampe", "ignored").replace("YAMPE", "IGNORED").replace(
            "additional maximum", "IGNORED"
        )

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "cpp" in url.lower():
                resp.text = cpp_html_no_cpp2
            elif "ei" in url.lower():
                resp.text = ei_html
            else:
                resp.text = "<html/>"
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026), \
             patch("cra_feed.parsers.cpp_ei.time.sleep"):
            result = cpp_ei.parse(session)

        cpp2 = result["cpp2"]
        assert cpp2["rate"] == 0.0
        assert cpp2["yampe"] == 0


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


# ---------------------------------------------------------------------------
# CPP parser – live-style fixture (th scope="row" year cells + definition links)
# ---------------------------------------------------------------------------

class TestCppParserLive:
    """Regression tests for CPP/CPP2 parsing against a live-style fixture.

    The live CRA page uses ``<th scope="row">`` for the Year column in data
    rows (not ``<td>``) and embeds ``<a>Definition</a>`` links in column
    headers.  The parser must handle both without breaking.
    """

    def test_cpp_rate_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _cpp2 = _parse_cpp_page(html)
        assert cpp["rate"] == pytest.approx(0.0595, abs=1e-5), \
            f"CPP rate should be 0.0595, got {cpp.get('rate')}"

    def test_cpp_ympe_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(html)
        assert cpp["ympe"] == 74600, f"YMPE should be 74600, got {cpp.get('ympe')}"

    def test_cpp_basic_exemption_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(html)
        assert cpp["basic_exemption"] == 3500, \
            f"Basic exemption should be 3500, got {cpp.get('basic_exemption')}"

    def test_cpp_selects_correct_year_live(self):
        """With 2024/2025/2026 rows, parser must pick 2026 (not earlier years)."""
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(html)
        assert cpp["ympe"] == 74600  # 2026 value, not 71300 (2025) or 68500 (2024)

    def test_cpp2_rate_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            _, cpp2 = _parse_cpp_page(html)
        assert cpp2["rate"] == pytest.approx(0.04, abs=1e-5), \
            f"CPP2 rate should be 0.04, got {cpp2.get('rate')}"

    def test_cpp2_yampe_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        html = _read_fixture("cpp_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            _, cpp2 = _parse_cpp_page(html)
        assert cpp2["yampe"] == 85000, f"YAMPE should be 85000, got {cpp2.get('yampe')}"


# ---------------------------------------------------------------------------
# CPP2 parser – dedicated CPP2 page fixture
# ---------------------------------------------------------------------------

class TestCpp2DedicatedPage:
    """Regression tests for CPP2 parsing from the dedicated CPP2 URL."""

    def test_cpp2_rate_from_dedicated_page(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp2_page
        html = _read_fixture("cpp2_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp2 = _parse_cpp2_page(html)
        assert cpp2["rate"] == pytest.approx(0.04, abs=1e-5), \
            f"CPP2 rate should be 0.04, got {cpp2.get('rate')}"

    def test_cpp2_yampe_from_dedicated_page(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp2_page
        html = _read_fixture("cpp2_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp2 = _parse_cpp2_page(html)
        assert cpp2["yampe"] == 85000, f"YAMPE should be 85000, got {cpp2.get('yampe')}"

    def test_cpp2_picks_correct_year(self):
        """With 2024/2025/2026 rows, parser must pick 2026."""
        from cra_feed.parsers.cpp_ei import _parse_cpp2_page
        html = _read_fixture("cpp2_page.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp2 = _parse_cpp2_page(html)
        assert cpp2["yampe"] == 85000  # 2026 value, not 81900 (2025) or 73200 (2024)


# ---------------------------------------------------------------------------
# EI parser – live-style fixture (th scope="row" year cells + definition links)
# ---------------------------------------------------------------------------

class TestEiParserLive:
    """Regression tests for EI parsing against a live-style fixture."""

    def test_ei_rate_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_ei_page
        html = _read_fixture("ei_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            ei = _parse_ei_page(html)
        assert ei["rate"] == pytest.approx(0.0163, abs=1e-5), \
            f"EI rate should be 0.0163, got {ei.get('rate')}"

    def test_ei_max_insurable_2026_live(self):
        from cra_feed.parsers.cpp_ei import _parse_ei_page
        html = _read_fixture("ei_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            ei = _parse_ei_page(html)
        assert ei["max_insurable_earnings"] == 68900, \
            f"Max insurable should be 68900, got {ei.get('max_insurable_earnings')}"

    def test_ei_selects_correct_year_live(self):
        """With 2024/2025/2026 rows, parser must pick 2026."""
        from cra_feed.parsers.cpp_ei import _parse_ei_page
        html = _read_fixture("ei_page_live.html")
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            ei = _parse_ei_page(html)
        assert ei["max_insurable_earnings"] == 68900  # 2026, not 65700 or 63200


# ---------------------------------------------------------------------------
# Province mapping – canonical keys, no "newfoundland" duplicate
# ---------------------------------------------------------------------------

class TestProvinceMapping:
    """Tests for the PROVINCE_NAME_TO_CODE canonical-key mapping."""

    # Quebec (QC) is intentionally excluded: it runs its own provincial tax
    # system (Revenu Québec) and is not covered by the T4127 formulas.
    EXPECTED_CODES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "SK", "YT"}

    def test_no_duplicate_nl_key(self):
        """'newfoundland' must not be a separate key from 'newfoundland and labrador'."""
        from cra_feed.parsers.t4127 import PROVINCE_NAME_TO_CODE
        assert "newfoundland" not in PROVINCE_NAME_TO_CODE, (
            "PROVINCE_NAME_TO_CODE must not contain bare 'newfoundland' "
            "(would produce a duplicate NL entry)"
        )

    def test_newfoundland_and_labrador_key_present(self):
        """'newfoundland and labrador' must be present and map to 'NL'."""
        from cra_feed.parsers.t4127 import PROVINCE_NAME_TO_CODE
        assert PROVINCE_NAME_TO_CODE.get("newfoundland and labrador") == "NL"

    def test_exactly_12_province_codes(self):
        """Exactly 12 distinct province/territory codes (QC excluded)."""
        from cra_feed.parsers.t4127 import PROVINCE_NAME_TO_CODE
        codes = set(PROVINCE_NAME_TO_CODE.values())
        assert len(codes) == 12, f"Expected 12 province codes, got {len(codes)}: {codes}"

    def test_all_expected_codes_present(self):
        """All 12 canonical province codes must be present."""
        from cra_feed.parsers.t4127 import PROVINCE_NAME_TO_CODE
        codes = set(PROVINCE_NAME_TO_CODE.values())
        missing = self.EXPECTED_CODES - codes
        assert not missing, f"Missing province codes: {missing}"

    def test_no_qc_code(self):
        """Quebec (QC) must not appear — it uses its own provincial tax system."""
        from cra_feed.parsers.t4127 import PROVINCE_NAME_TO_CODE
        assert "QC" not in PROVINCE_NAME_TO_CODE.values(), (
            "Quebec must be excluded from PROVINCE_NAME_TO_CODE"
        )


# ---------------------------------------------------------------------------
# Province BPA – missing BPA must raise ValueError (not silent $0)
# ---------------------------------------------------------------------------

class TestProvinceBpaError:
    """Tests that a missing BPA raises ValueError, not silently returns $0."""

    def test_missing_bpa_raises_value_error(self):
        """_parse_province_bpa must raise ValueError when no BPA is found."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_province_bpa

        # Section with a tax table but no BPA dollar amount in the plausible range.
        html = """
        <div>
          <h3>Some Province provincial tax</h3>
          <table>
            <tr><th>Annual net income (A)</th><th>Rate (R)</th></tr>
            <tr><td>0 to 100,000</td><td>10%</td></tr>
          </table>
        </div>
        """
        section_soup = BeautifulSoup(html, "lxml")

        with pytest.raises(ValueError, match="Could not parse BPA"):
            _parse_province_bpa(section_soup, "some province")

    def test_missing_bpa_does_not_return_zero(self):
        """_parse_province_bpa must NOT silently return 0.0 when BPA is absent."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_province_bpa

        html = "<div><p>No basic personal amount here.</p></div>"
        section_soup = BeautifulSoup(html, "lxml")

        raised = False
        try:
            result = _parse_province_bpa(section_soup, "testprovince")
        except ValueError:
            raised = True

        assert raised, (
            "_parse_province_bpa must raise ValueError for missing BPA, "
            "not return a value (got 0.0 or similar)"
        )

    def test_present_bpa_is_parsed_correctly(self):
        """Verify the function still parses a well-formed BPA section."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_province_bpa

        html = """
        <div>
          <p>Basic personal amount: $11,865.00</p>
        </div>
        """
        section_soup = BeautifulSoup(html, "lxml")
        bpa = _parse_province_bpa(section_soup, "ontario")
        assert bpa == pytest.approx(11865.0, abs=1.0)

    def test_bpa_in_bulleted_list(self):
        """_parse_province_bpa must find BPA expressed in a <ul><li> element."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_province_bpa

        html = """
        <div>
          <ul>
            <li>The basic personal amount for this province is $12,000.00</li>
          </ul>
        </div>
        """
        section_soup = BeautifulSoup(html, "lxml")
        bpa = _parse_province_bpa(section_soup, "some province")
        assert bpa == pytest.approx(12000.0, abs=1.0)

