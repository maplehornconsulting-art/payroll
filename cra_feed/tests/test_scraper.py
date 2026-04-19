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
        result = _parse_province_bpa(section_soup, "ontario")
        assert result["bpa"] == pytest.approx(11865.0, abs=1.0)

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
        result = _parse_province_bpa(section_soup, "some province")
        assert result["bpa"] == pytest.approx(12000.0, abs=1.0)


# ---------------------------------------------------------------------------
# Province BPA – claim codes table strategy (BC, NL, NT, NU)
# ---------------------------------------------------------------------------

class TestProvinceBpaFromClaimCodes:
    """Tests for the claim-codes-table BPA extraction strategy (Strategy 5)."""

    def _bc_section_soup(self):
        from bs4 import BeautifulSoup
        html = (FIXTURES_DIR / "t4127_bc_claim_codes.html").read_text(encoding="utf-8")
        return BeautifulSoup(html, "lxml")

    def _nl_section_soup(self):
        from bs4 import BeautifulSoup
        html = (FIXTURES_DIR / "t4127_nl_claim_codes.html").read_text(encoding="utf-8")
        return BeautifulSoup(html, "lxml")

    def test_bc_bpa_from_claim_codes(self):
        """BC BPA must be extracted from claim code 1's 'Total claim amount to' cell."""
        from cra_feed.parsers.t4127 import _parse_province_bpa

        result = _parse_province_bpa(self._bc_section_soup(), "british columbia")
        assert result["bpa"] == pytest.approx(13216.0, abs=0.01)

    def test_bc_k1p_from_claim_codes(self):
        """BC K1P must be extracted from claim code 1's 'Option 1, K1P ($)' cell."""
        from cra_feed.parsers.t4127 import _parse_province_bpa

        result = _parse_province_bpa(self._bc_section_soup(), "british columbia")
        assert "k1p" in result, "k1p must be present in result when claim codes table found"
        assert result["k1p"] == pytest.approx(668.73, abs=0.01)

    def test_falls_back_only_when_standalone_bpa_missing(self):
        """When a standalone BPA line is present, use it (claim codes are NOT consulted)."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_province_bpa

        # Combine a standalone BPA paragraph with the BC claim codes table.
        # The standalone BPA ($9,999.00) must win over the claim code 1 value.
        standalone_html = """
        <div>
          <p>Basic personal amount: $9,999.00</p>
          <table>
            <caption>Table 8.11 British Columbia claim codes</caption>
            <thead>
              <tr>
                <th>Claim code</th>
                <th>Total claim amount ($) from</th>
                <th>Total claim amount ($) to</th>
                <th>Option 1, TCP ($)</th>
                <th>Option 1, K1P ($)</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td><td>0.00</td></tr>
              <tr><td>1</td><td>0.00</td><td>13,216.00</td><td>13,216.00</td><td>668.73</td></tr>
            </tbody>
          </table>
        </div>
        """
        section_soup = BeautifulSoup(standalone_html, "lxml")
        result = _parse_province_bpa(section_soup, "british columbia")
        assert result["bpa"] == pytest.approx(9999.0, abs=0.01), (
            "Standalone BPA must take priority over claim codes table"
        )

    def test_raises_when_neither_present(self):
        """An empty section must still raise ValueError (no silent $0 fallback)."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_province_bpa

        section_soup = BeautifulSoup("<div><p>No tax data here.</p></div>", "lxml")
        with pytest.raises(ValueError, match="Could not parse BPA"):
            _parse_province_bpa(section_soup, "british columbia")

    def test_nl_bpa_from_claim_codes(self):
        """Multi-word province name 'Newfoundland and Labrador' must also work."""
        from cra_feed.parsers.t4127 import _parse_province_bpa

        result = _parse_province_bpa(self._nl_section_soup(), "newfoundland and labrador")
        assert result["bpa"] == pytest.approx(10900.0, abs=0.01)

    def test_nl_k1p_from_claim_codes(self):
        """NL K1P must be extracted correctly from the claim codes table."""
        from cra_feed.parsers.t4127 import _parse_province_bpa

        result = _parse_province_bpa(self._nl_section_soup(), "newfoundland and labrador")
        assert "k1p" in result
        assert result["k1p"] == pytest.approx(948.30, abs=0.01)

    def test_parse_one_province_bc_includes_k1p(self):
        """_parse_one_province must propagate k1p from _parse_province_bpa."""
        from cra_feed.parsers.t4127 import _parse_one_province

        result = _parse_one_province(self._bc_section_soup(), "british columbia", "BC")
        assert result is not None
        assert result["bpa"] == pytest.approx(13216.0, abs=0.01)
        assert "k1p" in result
        assert result["k1p"] == pytest.approx(668.73, abs=0.01)


# ---------------------------------------------------------------------------
# _clean_header_text unit tests
# ---------------------------------------------------------------------------

class TestCleanHeaderText:
    """Unit tests for the _clean_header_text() helper."""

    def _th(self, inner_html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(f"<th>{inner_html}</th>", "lxml").find("th")

    def test_strips_wb_inv(self):
        """wb-inv span (screen-reader duplicate text) must be removed."""
        from cra_feed.parsers.cpp_ei import _clean_header_text
        th = self._th('Rate <span class="wb-inv">: Rate</span>')
        assert _clean_header_text(th) == "Rate"

    def test_strips_definition_link(self):
        """<a class="small">definition...</a> helper link must be removed."""
        from cra_feed.parsers.cpp_ei import _clean_header_text
        th = self._th(
            'Rate <a class="small">definition'
            '<span class="wb-inv">: Rate</span></a>'
        )
        assert _clean_header_text(th) == "Rate"

    def test_strips_fontawesome_icon(self):
        """FontAwesome icon spans (far/fa-*) must be removed."""
        from cra_feed.parsers.cpp_ei import _clean_header_text
        th = self._th('Rate <span class="far fa-question-circle"></span>')
        assert _clean_header_text(th) == "Rate"

    def test_collapses_whitespace_with_br(self):
        """<br> line breaks between words must be collapsed to single space."""
        from cra_feed.parsers.cpp_ei import _clean_header_text
        th = self._th("Maximum<br>annual<br>rate")
        assert _clean_header_text(th) == "Maximum annual rate"

    def test_preserves_simple_text(self):
        """Plain text with no noise elements must pass through unchanged."""
        from cra_feed.parsers.cpp_ei import _clean_header_text
        th = self._th("Year")
        assert _clean_header_text(th) == "Year"


# ---------------------------------------------------------------------------
# Regression test: exact user-captured live HTML excerpt
# ---------------------------------------------------------------------------

class TestCppLiveHtmlRegression:
    """Regression test using a fixture that exactly matches the user-pasted
    live HTML excerpt from the canada.ca CPP page.

    Verifies CPP rate=0.0595, YMPE=74600, basic exemption=3500 for 2026.
    """

    _FIXTURE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"></head>
<body><main>
<table class="table table-striped">
<thead>
<tr>
<th scope="col">Year</th>
<th scope="col">Maximum<br class="visible-xs">
annual<br class="visible-xs">
pensionable<br class="visible-xs">
earnings&nbsp;<br>
<a href="#dt1" class="small">definition
  <span class="wb-inv">: Maximum annual pensionable earnings (YMPE)</span>
  <span class="far fa-question-circle mrgn-lft-0"></span>
</a>
(YMPE)
</th>
<th scope="col">Basic<br class="visible-xs">
exemption<br class="visible-xs">
amount&nbsp;<br>
<a href="#dt2" class="small">definition
  <span class="wb-inv">: Basic exemption amount</span>
  <span class="far fa-question-circle mrgn-lft-0"></span>
</a>
</th>
<th scope="col">Maximum<br class="visible-xs">
contributory<br class="visible-xs">
earnings&nbsp;<br>
<a href="#dt3" class="small">definition
  <span class="wb-inv">: Maximum contributory earnings</span>
  <span class="far fa-question-circle mrgn-lft-0"></span>
</a>
</th>
<th scope="col">Employee<br class="visible-xs">
and employer<br class="visible-xs">
contribution<br class="visible-xs">
rate (%)&nbsp;<br>
<a href="#dt4" class="small">definition
  <span class="wb-inv">: Employee and employer contribution rate (%)</span>
  <span class="far fa-question-circle mrgn-lft-0"></span>
</a>
</th>
<th scope="col">Maximum<br class="visible-xs">
annual<br class="visible-xs">
employee and<br class="visible-xs">
employer<br class="visible-xs">
contribution&nbsp;<br>
<a href="#dt5" class="small">definition
  <span class="wb-inv">: Maximum annual employee and employer contribution</span>
  <span class="far fa-question-circle mrgn-lft-0"></span>
</a>
</th>
<th scope="col">Maximum<br class="visible-xs">
annual<br class="visible-xs">
self-employed<br class="visible-xs">
contribution&nbsp;<br>
<a href="#dt6" class="small">definition
  <span class="wb-inv">: Maximum annual self-employed contribution</span>
  <span class="far fa-question-circle mrgn-lft-0"></span>
</a>
</th>
</tr>
</thead>
<tbody>
<tr>
<td>2026</td><td>$74,600</td><td>$3,500</td><td>$71,100</td><td>5.95</td><td>$4,230.45</td><td>$8,460.90</td>
</tr>
<tr>
<td>2025</td><td>$71,300</td><td>$3,500</td><td>$67,800</td><td>5.95</td><td>$4,034.10</td><td>$8,068.20</td>
</tr>
</tbody>
</table>
</main></body></html>"""

    def test_cpp_rate_from_live_excerpt(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(self._FIXTURE)
        assert cpp["rate"] == pytest.approx(0.0595, abs=1e-5)

    def test_cpp_ympe_from_live_excerpt(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(self._FIXTURE)
        assert cpp["ympe"] == 74600

    def test_cpp_basic_exemption_from_live_excerpt(self):
        from cra_feed.parsers.cpp_ei import _parse_cpp_page
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = _parse_cpp_page(self._FIXTURE)
        assert cpp["basic_exemption"] == 3500


# ---------------------------------------------------------------------------
# debug_dir: HTML is written on parse failure
# ---------------------------------------------------------------------------

class TestCppEiDebugDir:
    """Tests that parse() writes debug HTML files when debug_dir is set."""

    def test_debug_cpp_html_written_on_failure(self, tmp_path):
        """When CPP parse fails (no valid year data), cpp.html is written."""
        from unittest.mock import MagicMock
        from cra_feed.parsers import cpp_ei

        broken_html = "<html><body><p>No table here</p></body></html>"
        valid_ei = _read_fixture("ei_page_live.html")

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "ei" in url.lower():
                resp.text = valid_ei
            else:
                resp.text = broken_html
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026), \
             patch("cra_feed.parsers.cpp_ei.time.sleep"):
            with pytest.raises(ValueError):
                cpp_ei.parse(session, debug_dir=tmp_path)

        assert (tmp_path / "cpp.html").exists(), "cpp.html must be written on CPP parse failure"

    def test_debug_ei_html_written_on_failure(self, tmp_path):
        """When EI parse fails (no valid year data), ei.html is written."""
        from unittest.mock import MagicMock
        from cra_feed.parsers import cpp_ei

        valid_cpp = _read_fixture("cpp_page_live.html")
        broken_html = "<html><body><p>No EI table here</p></body></html>"

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "ei" in url.lower():
                resp.text = broken_html
            else:
                resp.text = valid_cpp
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026), \
             patch("cra_feed.parsers.cpp_ei.time.sleep"):
            with pytest.raises(ValueError):
                cpp_ei.parse(session, debug_dir=tmp_path)

        assert (tmp_path / "ei.html").exists(), "ei.html must be written on EI parse failure"


# ---------------------------------------------------------------------------
# _parse_table_81 unit tests
# ---------------------------------------------------------------------------

class TestParseTable81:
    """Unit tests for _parse_table_81() using synthetic HTML fixtures."""

    _HTML = """
    <html><body>
    <table>
      <caption>Table 8.1 Rates (R, V), income thresholds (A), and constants (K, KP) for 2026</caption>
      <thead>
        <tr><th></th><th>1st</th><th>2nd</th><th>3rd</th><th>4th</th><th>5th</th><th>6th</th><th>7th</th></tr>
      </thead>
      <tbody>
        <!-- Federal block – must be ignored -->
        <tr><td>Federal</td><td>A</td><td>0</td><td>58,523</td><td>117,045</td><td>181,440</td><td>258,482</td><td></td></tr>
        <tr><td>R</td><td>0.1400</td><td>0.2050</td><td>0.2600</td><td>0.2900</td><td>0.3300</td><td></td><td></td></tr>
        <tr><td>K</td><td>0</td><td>3,804</td><td>10,241</td><td>15,685</td><td>26,024</td><td></td><td></td></tr>
        <!-- AB – 6 brackets -->
        <tr><td>AB</td><td>A</td><td>0</td><td>61,200</td><td>154,259</td><td>185,111</td><td>246,813</td><td>370,220</td></tr>
        <tr><td>V</td><td>0.0800</td><td>0.1000</td><td>0.1200</td><td>0.1300</td><td>0.1400</td><td>0.1500</td><td></td></tr>
        <tr><td>KP</td><td>0</td><td>1,224</td><td>4,309</td><td>6,160</td><td>8,628</td><td>12,331</td><td></td></tr>
        <!-- NU – 4 brackets -->
        <tr><td>NU</td><td>A</td><td>0</td><td>55,801</td><td>111,602</td><td>181,439</td><td></td><td></td></tr>
        <tr><td>V</td><td>0.0400</td><td>0.0700</td><td>0.0900</td><td>0.1150</td><td></td><td></td><td></td></tr>
        <tr><td>KP</td><td>0</td><td>1,624</td><td>5,278</td><td>9,826</td><td></td><td></td><td></td></tr>
      </tbody>
    </table>
    </body></html>
    """

    @pytest.fixture(scope="class")
    def result(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_table_81
        soup = BeautifulSoup(self._HTML, "lxml")
        return _parse_table_81(soup)

    def test_federal_not_included(self, result):
        """Federal block must be ignored."""
        assert "Federal" not in result
        # No province code for Federal
        assert all(len(k) == 2 for k in result)

    def test_returns_ab_and_nu(self, result):
        assert "AB" in result
        assert "NU" in result

    def test_ab_bracket_count(self, result):
        assert len(result["AB"]) == 6

    def test_ab_rates(self, result):
        rates = [b["rate"] for b in result["AB"]]
        assert rates == pytest.approx([0.08, 0.10, 0.12, 0.13, 0.14, 0.15], abs=1e-5)

    def test_ab_thresholds(self, result):
        up_tos = [b["up_to"] for b in result["AB"]]
        assert up_tos[:5] == pytest.approx([61200.0, 154259.0, 185111.0, 246813.0, 370220.0])
        assert up_tos[-1] is None

    def test_ab_top_bracket_none(self, result):
        assert result["AB"][-1]["up_to"] is None

    def test_nu_bracket_count(self, result):
        assert len(result["NU"]) == 4

    def test_nu_brackets_exact(self, result):
        expected = [
            {"up_to": 55801.0, "rate": pytest.approx(0.04, abs=1e-5)},
            {"up_to": 111602.0, "rate": pytest.approx(0.07, abs=1e-5)},
            {"up_to": 181439.0, "rate": pytest.approx(0.09, abs=1e-5)},
            {"up_to": None, "rate": pytest.approx(0.115, abs=1e-5)},
        ]
        for actual, exp in zip(result["NU"], expected):
            assert actual["up_to"] == exp["up_to"]
            assert actual["rate"] == exp["rate"]

    def test_nu_top_bracket_none(self, result):
        assert result["NU"][-1]["up_to"] is None

    def test_returns_empty_when_no_table_81(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_table_81
        soup = BeautifulSoup("<html><body><p>No table here</p></body></html>", "lxml")
        assert _parse_table_81(soup) == {}


# ---------------------------------------------------------------------------
# _parse_claim_code_bpas unit tests
# ---------------------------------------------------------------------------

class TestParseClaimCodeBpas:
    """Unit tests for _parse_claim_code_bpas() using synthetic HTML fixtures."""

    _HTML = """
    <html><body>
    <!-- NU claim codes table – has K1P -->
    <table>
      <caption>Table 8.17 Nunavut claim codes</caption>
      <thead>
        <tr>
          <th>Claim code</th>
          <th>Total claim amount ($) from</th>
          <th>Total claim amount ($) to</th>
          <th>Option 1, TCP ($)</th>
          <th>Option 1, K1P ($)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td><td>0.00</td></tr>
        <tr><td>1</td><td>0.00</td><td>19,659.00</td><td>19,659.00</td><td>786.36</td></tr>
        <tr><td>2</td><td>19,659.01</td><td>39,318.00</td><td>39,318.00</td><td>1,572.72</td></tr>
      </tbody>
    </table>
    <!-- MB claim codes table – parenthetical suffix, no K1P column -->
    <table>
      <caption>Table 8.13 Manitoba (Using maximum BPAMB) claim codes</caption>
      <thead>
        <tr>
          <th>Claim code</th>
          <th>Total claim amount ($) from</th>
          <th>Total claim amount ($) to</th>
          <th>Option 1, TCP ($)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td></tr>
        <tr><td>1</td><td>0.00</td><td>15,780.00</td><td>15,780.00</td></tr>
        <tr><td>2</td><td>15,780.01</td><td>31,560.00</td><td>31,560.00</td></tr>
      </tbody>
    </table>
    </body></html>
    """

    @pytest.fixture(scope="class")
    def result(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_claim_code_bpas
        soup = BeautifulSoup(self._HTML, "lxml")
        return _parse_claim_code_bpas(soup)

    def test_nu_present(self, result):
        assert "NU" in result

    def test_nu_bpa(self, result):
        assert result["NU"]["bpa"] == pytest.approx(19659.0, abs=0.01)

    def test_nu_k1p_present(self, result):
        assert "k1p" in result["NU"]

    def test_nu_k1p_value(self, result):
        assert result["NU"]["k1p"] == pytest.approx(786.36, abs=0.01)

    def test_mb_present(self, result):
        assert "MB" in result

    def test_mb_bpa(self, result):
        assert result["MB"]["bpa"] == pytest.approx(15780.0, abs=0.01)

    def test_mb_no_k1p(self, result):
        """MB table has no K1P column; k1p key must be absent."""
        assert "k1p" not in result["MB"]

    def test_returns_empty_when_no_tables(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_claim_code_bpas
        soup = BeautifulSoup("<html><body><p>Nothing here</p></body></html>", "lxml")
        assert _parse_claim_code_bpas(soup) == {}


# ---------------------------------------------------------------------------
# _parse_provinces integration test (2026+ Table 8.1 format)
# ---------------------------------------------------------------------------

class TestParseProvincesTable81:
    """Integration test for _parse_provinces() using the 2026+ Table 8.1 format."""

    _HTML = """
    <html><body>
    <!-- Table 8.1: consolidated brackets -->
    <table>
      <caption>Table 8.1 Rates (R, V), income thresholds (A), and constants (K, KP) for 2026</caption>
      <thead>
        <tr><th></th><th>1st</th><th>2nd</th><th>3rd</th><th>4th</th><th>5th</th><th>6th</th></tr>
      </thead>
      <tbody>
        <tr><td>AB</td><td>A</td><td>0</td><td>61,200</td><td>154,259</td><td>185,111</td><td>246,813</td></tr>
        <tr><td>V</td><td>0.0800</td><td>0.1000</td><td>0.1200</td><td>0.1300</td><td>0.1400</td><td></td></tr>
        <tr><td>KP</td><td>0</td><td>1,224</td><td>4,309</td><td>6,160</td><td>8,628</td><td></td></tr>
        <tr><td>NU</td><td>A</td><td>0</td><td>55,801</td><td>111,602</td><td>181,439</td><td></td></tr>
        <tr><td>V</td><td>0.0400</td><td>0.0700</td><td>0.0900</td><td>0.1150</td><td></td><td></td></tr>
        <tr><td>KP</td><td>0</td><td>1,624</td><td>5,278</td><td>9,826</td><td></td><td></td></tr>
      </tbody>
    </table>
    <!-- Claim codes tables for AB and NU -->
    <table>
      <caption>Table 8.10 Alberta claim codes</caption>
      <thead>
        <tr>
          <th>Claim code</th>
          <th>Total claim amount ($) from</th>
          <th>Total claim amount ($) to</th>
          <th>Option 1, TCP ($)</th>
          <th>Option 1, K1P ($)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td><td>0.00</td></tr>
        <tr><td>1</td><td>0.00</td><td>21,003.00</td><td>21,003.00</td><td>1,680.24</td></tr>
      </tbody>
    </table>
    <table>
      <caption>Table 8.17 Nunavut claim codes</caption>
      <thead>
        <tr>
          <th>Claim code</th>
          <th>Total claim amount ($) from</th>
          <th>Total claim amount ($) to</th>
          <th>Option 1, TCP ($)</th>
          <th>Option 1, K1P ($)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td><td>0.00</td></tr>
        <tr><td>1</td><td>0.00</td><td>19,659.00</td><td>19,659.00</td><td>786.36</td></tr>
      </tbody>
    </table>
    </body></html>
    """

    @pytest.fixture(scope="class")
    def provinces(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_provinces
        soup = BeautifulSoup(self._HTML, "lxml")
        return _parse_provinces(soup)

    def test_both_provinces_present(self, provinces):
        assert "AB" in provinces
        assert "NU" in provinces

    def test_ab_bpa(self, provinces):
        assert provinces["AB"]["bpa"] == pytest.approx(21003.0, abs=0.01)

    def test_ab_k1p(self, provinces):
        assert "k1p" in provinces["AB"]
        assert provinces["AB"]["k1p"] == pytest.approx(1680.24, abs=0.01)

    def test_ab_tax_brackets(self, provinces):
        brackets = provinces["AB"]["tax_brackets"]
        assert len(brackets) == 5  # 5 rates in the V row
        assert brackets[-1]["up_to"] is None

    def test_nu_bpa(self, provinces):
        assert provinces["NU"]["bpa"] == pytest.approx(19659.0, abs=0.01)

    def test_nu_k1p(self, provinces):
        assert "k1p" in provinces["NU"]
        assert provinces["NU"]["k1p"] == pytest.approx(786.36, abs=0.01)

    def test_nu_tax_brackets(self, provinces):
        brackets = provinces["NU"]["tax_brackets"]
        assert len(brackets) == 4
        assert brackets[-1]["up_to"] is None

    def test_nu_bracket_values(self, provinces):
        brackets = provinces["NU"]["tax_brackets"]
        assert brackets[0] == {"up_to": pytest.approx(55801.0), "rate": pytest.approx(0.04)}
        assert brackets[1] == {"up_to": pytest.approx(111602.0), "rate": pytest.approx(0.07)}
        assert brackets[2] == {"up_to": pytest.approx(181439.0), "rate": pytest.approx(0.09)}
        assert brackets[3] == {"up_to": None, "rate": pytest.approx(0.115)}

    def test_missing_bpa_raises_value_error(self):
        """When Table 8.1 has brackets but no matching claim codes table, raise."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_provinces
        html = """
        <html><body>
        <table>
          <caption>Table 8.1 Rates (R, V), income thresholds (A), and constants (K, KP) for 2026</caption>
          <tbody>
            <tr><td>NU</td><td>A</td><td>0</td><td>55,801</td><td>111,602</td><td>181,439</td></tr>
            <tr><td>V</td><td>0.0400</td><td>0.0700</td><td>0.0900</td><td>0.1150</td></tr>
          </tbody>
        </table>
        <!-- No claim codes table for NU -->
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        with pytest.raises(ValueError, match="NU"):
            _parse_provinces(soup)

    def test_falls_back_to_legacy_when_no_table_81(self):
        """When Table 8.1 is absent, legacy per-province parsing must be attempted."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_provinces
        # Page with no Table 8.1 but a legacy-style province section
        html = """
        <html><body>
        <h3>Ontario</h3>
        <p>Basic personal amount: $11,865.00</p>
        <table>
          <caption>Ontario provincial tax rates</caption>
          <tr><th>Income</th><th>Rate</th></tr>
          <tr><td>$0 to $51,446</td><td>5.05%</td></tr>
          <tr><td>$51,447 to $102,894</td><td>9.15%</td></tr>
          <tr><td>Over $102,894</td><td>11.16%</td></tr>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _parse_provinces(soup)
        assert "ON" in result
        assert result["ON"]["bpa"] == pytest.approx(11865.0, abs=0.01)
        assert len(result["ON"]["tax_brackets"]) == 3


# ---------------------------------------------------------------------------
# _parse_table_82_surtaxes unit tests
# ---------------------------------------------------------------------------

class TestParseTable82Surtaxes:
    """Unit tests for _parse_table_82_surtaxes() using a synthetic HTML fixture."""

    _HTML = """
    <html><body>
    <table>
      <caption>Table 8.2 Other rates and amounts for 2026</caption>
      <thead>
        <tr>
          <th>Province</th>
          <th>Surtax threshold 1 ($)</th>
          <th>Surtax rate 1 (V1)</th>
          <th>Surtax threshold 2 ($)</th>
          <th>Surtax rate 2 (V2)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>ON</td>
          <td>$5,818</td>
          <td>20%</td>
          <td>$7,446</td>
          <td>36%</td>
        </tr>
      </tbody>
    </table>
    </body></html>
    """

    @pytest.fixture(scope="class")
    def result(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_table_82_surtaxes
        soup = BeautifulSoup(self._HTML, "lxml")
        return _parse_table_82_surtaxes(soup)

    def test_on_present(self, result):
        assert "ON" in result

    def test_on_two_bands(self, result):
        assert len(result["ON"]) == 2

    def test_on_first_band(self, result):
        assert result["ON"][0][0] == pytest.approx(5818.0)
        assert result["ON"][0][1] == pytest.approx(0.20)

    def test_on_second_band(self, result):
        assert result["ON"][1][0] == pytest.approx(7446.0)
        assert result["ON"][1][1] == pytest.approx(0.36)

    def test_exact_value(self, result):
        assert result == {"ON": [[5818.0, 0.20], [7446.0, 0.36]]}

    def test_returns_empty_when_no_table_82(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_table_82_surtaxes
        soup = BeautifulSoup("<html><body><p>No table here</p></body></html>", "lxml")
        assert _parse_table_82_surtaxes(soup) == {}

    def test_returns_empty_when_no_surtax_data(self):
        """Table 8.2 present but with no province rows → empty dict."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_table_82_surtaxes
        html = """
        <html><body>
        <table>
          <caption>Table 8.2 Other rates and amounts for 2026</caption>
          <thead><tr><th>Column A</th><th>Column B</th></tr></thead>
          <tbody></tbody>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _parse_table_82_surtaxes(soup) == {}

    def test_decimal_rate_format(self):
        """Parser must also accept decimal rate format (0.20 instead of 20%)."""
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_table_82_surtaxes
        html = """
        <html><body>
        <table>
          <caption>Table 8.2 Other rates and amounts for 2026</caption>
          <tbody>
            <tr><td>ON</td><td>$5,818</td><td>0.20</td><td>$7,446</td><td>0.36</td></tr>
          </tbody>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _parse_table_82_surtaxes(soup)
        assert result == {"ON": [[5818.0, 0.20], [7446.0, 0.36]]}


# ---------------------------------------------------------------------------
# _parse_provinces integration test — surtax key present on every province
# ---------------------------------------------------------------------------

class TestParseProvincesTable81Surtax:
    """Integration tests for _parse_provinces() surtax injection."""

    _HTML = """
    <html><body>
    <!-- Table 8.1: consolidated brackets -->
    <table>
      <caption>Table 8.1 Rates (R, V), income thresholds (A), and constants (K, KP) for 2026</caption>
      <thead>
        <tr><th></th><th>1st</th><th>2nd</th><th>3rd</th><th>4th</th><th>5th</th><th>6th</th></tr>
      </thead>
      <tbody>
        <tr><td>AB</td><td>A</td><td>0</td><td>61,200</td><td>154,259</td><td>185,111</td><td>246,813</td></tr>
        <tr><td>V</td><td>0.0800</td><td>0.1000</td><td>0.1200</td><td>0.1300</td><td>0.1400</td><td></td></tr>
        <tr><td>KP</td><td>0</td><td>1,224</td><td>4,309</td><td>6,160</td><td>8,628</td><td></td></tr>
        <tr><td>ON</td><td>A</td><td>0</td><td>53,891</td><td>107,785</td><td>150,000</td><td>220,000</td></tr>
        <tr><td>V</td><td>0.0505</td><td>0.0915</td><td>0.1116</td><td>0.1216</td><td>0.1316</td><td></td></tr>
        <tr><td>KP</td><td>0</td><td>2,158</td><td>4,831</td><td>7,341</td><td>9,541</td><td></td></tr>
      </tbody>
    </table>
    <!-- Claim codes for AB and ON -->
    <table>
      <caption>Table 8.10 Alberta claim codes</caption>
      <thead>
        <tr>
          <th>Claim code</th>
          <th>Total claim amount ($) from</th>
          <th>Total claim amount ($) to</th>
          <th>Option 1, TCP ($)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td></tr>
        <tr><td>1</td><td>0.00</td><td>21,003.00</td><td>21,003.00</td></tr>
      </tbody>
    </table>
    <table>
      <caption>Table 8.12 Ontario claim codes</caption>
      <thead>
        <tr>
          <th>Claim code</th>
          <th>Total claim amount ($) from</th>
          <th>Total claim amount ($) to</th>
          <th>Option 1, TCP ($)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>0</td><td>No claim amount</td><td>No claim amount</td><td>0.00</td></tr>
        <tr><td>1</td><td>0.00</td><td>12,989.00</td><td>12,989.00</td></tr>
      </tbody>
    </table>
    <!-- Table 8.2: ON surtax -->
    <table>
      <caption>Table 8.2 Other rates and amounts for 2026</caption>
      <tbody>
        <tr>
          <td>ON</td>
          <td>$5,818</td>
          <td>20%</td>
          <td>$7,446</td>
          <td>36%</td>
        </tr>
      </tbody>
    </table>
    </body></html>
    """

    @pytest.fixture(scope="class")
    def provinces(self):
        from bs4 import BeautifulSoup
        from cra_feed.parsers.t4127 import _parse_provinces
        soup = BeautifulSoup(self._HTML, "lxml")
        return _parse_provinces(soup)

    def test_on_surtax_present(self, provinces):
        assert "surtax" in provinces["ON"]

    def test_on_surtax_values(self, provinces):
        assert provinces["ON"]["surtax"] == [[5818.0, 0.20], [7446.0, 0.36]]

    def test_ab_surtax_present(self, provinces):
        assert "surtax" in provinces["AB"]

    def test_ab_surtax_empty(self, provinces):
        assert provinces["AB"]["surtax"] == []


# ---------------------------------------------------------------------------
# ProvinceData surtax round-trip and validate_feed regression tests
# ---------------------------------------------------------------------------

class TestProvinceDataSurtaxRoundTrip:
    """Regression tests: surtax is preserved through ProvinceData model_dump()."""

    def test_on_surtax_preserved(self):
        from cra_feed.schema import ProvinceData, TaxBracket
        pdata = {
            "bpa": 12989.0,
            "tax_brackets": [{"up_to": 53891.0, "rate": 0.0505}, {"up_to": None, "rate": 0.1316}],
            "surtax": [[5818.0, 0.20], [7446.0, 0.36]],
        }
        province = ProvinceData(
            bpa=pdata["bpa"],
            tax_brackets=[TaxBracket(**b) for b in pdata["tax_brackets"]],
            surtax=pdata.get("surtax", []),
            k1p=pdata.get("k1p"),
        )
        dumped = province.model_dump()
        assert dumped["surtax"] == [[5818.0, 0.20], [7446.0, 0.36]]

    def test_ab_surtax_empty_preserved(self):
        from cra_feed.schema import ProvinceData, TaxBracket
        pdata = {
            "bpa": 22769.0,
            "tax_brackets": [{"up_to": 61200.0, "rate": 0.08}, {"up_to": None, "rate": 0.15}],
            "surtax": [],
        }
        province = ProvinceData(
            bpa=pdata["bpa"],
            tax_brackets=[TaxBracket(**b) for b in pdata["tax_brackets"]],
            surtax=pdata.get("surtax", []),
            k1p=pdata.get("k1p"),
        )
        dumped = province.model_dump()
        assert dumped["surtax"] == []

    def test_validate_feed_accepts_surtax(self):
        """validate_feed must not raise when every province has a surtax field."""
        import copy
        from cra_feed.validate import validate_feed
        from cra_feed.tests.test_validate import VALID_FEED
        feed = copy.deepcopy(VALID_FEED)
        validate_feed(feed)  # should not raise

    def test_validate_feed_rejects_missing_surtax(self):
        """validate_feed must raise ValidationError when surtax is absent."""
        import copy
        import jsonschema
        from cra_feed.validate import validate_feed
        from cra_feed.tests.test_validate import VALID_FEED
        feed = copy.deepcopy(VALID_FEED)
        del feed["provinces"]["ON"]["surtax"]
        with pytest.raises(jsonschema.ValidationError):
            validate_feed(feed)
