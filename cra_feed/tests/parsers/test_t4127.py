"""Tests for the T4127 multi-strategy federal bracket locator.

Five fixtures exercise each code path:

* styleA  – heading matches Strategy A candidate #1
            ("Federal income tax rates and income thresholds")
* styleB  – heading matches Strategy A candidate #4 ("Federal tax rates")
* styleC  – no matching heading; Strategy B (fingerprint) must succeed
* styleE  – 2026+ bulleted-list format; Strategy E must succeed
* no_table – no bracket table at all; ValueError must be raised with the
             source URL and --debug-html hint in the message
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from cra_feed.parsers.t4127 import _parse_federal, _find_document_url, _has_t4127_content

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Expected brackets common to styleA / styleB / styleC fixtures.
_EXPECTED_RATES = [0.15, 0.205, 0.26, 0.29, 0.33]
_EXPECTED_FIRST_THRESHOLD = pytest.approx(57_375.0)
_EXPECTED_BPAF_MAX = pytest.approx(16_129.0)
_EXPECTED_BPAF_MIN = pytest.approx(14_538.0)


def _load(name: str) -> BeautifulSoup:
    html = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# Strategy A – heading phrase "Federal income tax rates and income thresholds"
# ---------------------------------------------------------------------------

class TestStyleA:
    """Strategy A succeeds on its first heading candidate."""

    @pytest.fixture(scope="class")
    def result(self):
        return _parse_federal(_load("t4127_federal_brackets_styleA.html"))

    def test_bracket_count(self, result):
        assert len(result["tax_brackets"]) == 5

    def test_bracket_rates(self, result):
        assert [b["rate"] for b in result["tax_brackets"]] == pytest.approx(
            _EXPECTED_RATES, abs=1e-4
        )

    def test_top_bracket_is_none(self, result):
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_first_threshold(self, result):
        assert result["tax_brackets"][0]["up_to"] == _EXPECTED_FIRST_THRESHOLD

    def test_bpaf_max(self, result):
        assert result["bpaf"]["max"] == _EXPECTED_BPAF_MAX

    def test_bpaf_min(self, result):
        assert result["bpaf"]["min"] == _EXPECTED_BPAF_MIN


# ---------------------------------------------------------------------------
# Strategy A – heading phrase "Federal tax rates" (later candidate)
# ---------------------------------------------------------------------------

class TestStyleB:
    """Strategy A succeeds on a later heading candidate ("Federal tax rates")."""

    @pytest.fixture(scope="class")
    def result(self):
        return _parse_federal(_load("t4127_federal_brackets_styleB.html"))

    def test_bracket_count(self, result):
        assert len(result["tax_brackets"]) == 5

    def test_bracket_rates(self, result):
        assert [b["rate"] for b in result["tax_brackets"]] == pytest.approx(
            _EXPECTED_RATES, abs=1e-4
        )

    def test_top_bracket_is_none(self, result):
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_first_threshold(self, result):
        assert result["tax_brackets"][0]["up_to"] == _EXPECTED_FIRST_THRESHOLD

    def test_bpaf_max(self, result):
        assert result["bpaf"]["max"] == _EXPECTED_BPAF_MAX

    def test_bpaf_min(self, result):
        assert result["bpaf"]["min"] == _EXPECTED_BPAF_MIN


# ---------------------------------------------------------------------------
# Strategy B – fingerprint (no matching heading)
# ---------------------------------------------------------------------------

class TestStyleC:
    """Strategy A fails; Strategy B (fingerprint) locates the bracket table."""

    @pytest.fixture(scope="class")
    def result(self):
        return _parse_federal(_load("t4127_federal_brackets_styleC.html"))

    def test_bracket_count(self, result):
        assert len(result["tax_brackets"]) == 5

    def test_bracket_rates(self, result):
        assert [b["rate"] for b in result["tax_brackets"]] == pytest.approx(
            _EXPECTED_RATES, abs=1e-4
        )

    def test_top_bracket_is_none(self, result):
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_first_threshold(self, result):
        assert result["tax_brackets"][0]["up_to"] == _EXPECTED_FIRST_THRESHOLD

    def test_bpaf_max(self, result):
        assert result["bpaf"]["max"] == _EXPECTED_BPAF_MAX

    def test_bpaf_min(self, result):
        assert result["bpaf"]["min"] == _EXPECTED_BPAF_MIN


# ---------------------------------------------------------------------------
# Regression – no bracket table → ValueError with URL and --debug-html hint
# ---------------------------------------------------------------------------

class TestNoTable:
    """All strategies fail; ValueError is raised with URL and debug hint."""

    def test_raises_value_error(self):
        soup = _load("t4127_federal_no_table.html")
        with pytest.raises(ValueError) as exc_info:
            _parse_federal(soup, source_url="https://example.com/t4127-jan.html")
        msg = str(exc_info.value)
        assert "https://example.com/t4127-jan.html" in msg
        assert "--debug-html" in msg

    def test_error_without_url(self):
        """source_url is optional; error must still be raised."""
        soup = _load("t4127_federal_no_table.html")
        with pytest.raises(ValueError, match="federal tax bracket table"):
            _parse_federal(soup)


# ---------------------------------------------------------------------------
# Regression – parse() must route the edition-page soup to _parse_federal
# ---------------------------------------------------------------------------

class TestParseEditionRouting:
    """Regression test for the NameError fix: parse() must use soup_edition.

    Before the fix, parse() called ``_parse_federal(soup_edition, ...)`` but
    ``soup_edition`` was never defined, causing a NameError at runtime.
    After the fix, ``soup_edition`` is built from the edition-page HTML and
    passed (not the index-page soup or any other soup) to ``_parse_federal``.
    """

    def test_parse_uses_edition_soup_not_index(self):
        """_parse_federal must receive the edition-page soup, not the index-page soup."""
        from unittest.mock import MagicMock, patch
        import cra_feed.parsers.t4127 as t4127_mod

        index_html = (FIXTURES_DIR / "t4127_index.html").read_text(encoding="utf-8")
        # styleA fixture contains bracket data — it serves as the edition page
        edition_html = (FIXTURES_DIR / "t4127_federal_brackets_styleA.html").read_text(
            encoding="utf-8"
        )

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            # The index URL returns the index fixture; any other URL returns edition fixture
            if url == t4127_mod.T4127_INDEX_URL:
                resp.text = index_html
            else:
                resp.text = edition_html
            return resp

        session.get.side_effect = _fake_get

        captured_soups: list = []
        original_parse_federal = t4127_mod._parse_federal

        def _spy(soup, **kwargs):
            captured_soups.append(soup)
            return original_parse_federal(soup, **kwargs)

        with patch.object(t4127_mod, "_parse_federal", side_effect=_spy), \
                patch("cra_feed.parsers.t4127.time.sleep"):
            result = t4127_mod.parse(session=session)

        # _parse_federal must have been called exactly once
        assert len(captured_soups) == 1, "_parse_federal should be called exactly once"

        # The soup passed in must NOT match the index-page soup (index has no brackets)
        index_soup = BeautifulSoup(index_html, "lxml")
        assert str(captured_soups[0]) != str(index_soup), (
            "_parse_federal must receive the edition-page soup, not the index-page soup"
        )

    def test_parse_returns_non_empty_tax_brackets(self):
        """parse() must return a non-empty tax_brackets list (no NameError)."""
        from unittest.mock import MagicMock, patch
        import cra_feed.parsers.t4127 as t4127_mod

        index_html = (FIXTURES_DIR / "t4127_index.html").read_text(encoding="utf-8")
        edition_html = (FIXTURES_DIR / "t4127_federal_brackets_styleA.html").read_text(
            encoding="utf-8"
        )

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.text = index_html if url == t4127_mod.T4127_INDEX_URL else edition_html
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.t4127.time.sleep"):
            result = t4127_mod.parse(session=session)

        assert result["tax_brackets"], "tax_brackets must not be empty"
        assert len(result["tax_brackets"]) > 0
        assert result["tax_brackets"][-1]["up_to"] is None, "top bracket up_to must be None"

    def test_parse_follows_toc_to_sub_page(self):
        """parse() must fetch and parse the sub-page when t4127-jan.html is a TOC.

        Regression test: before this fix, parse() passed ``soup_edition`` (the
        TOC page with no bracket tables) to ``_parse_federal``, causing a
        ValueError.  Now it detects the TOC, follows the computer-programs link,
        fetches the sub-page, and parses THAT instead.
        """
        from unittest.mock import MagicMock, patch
        import cra_feed.parsers.t4127 as t4127_mod

        index_html = (FIXTURES_DIR / "t4127_index.html").read_text(encoding="utf-8")
        # edition page is a TOC with no bracket tables — it links to the doc sub-page
        edition_html = (FIXTURES_DIR / "t4127_edition.html").read_text(encoding="utf-8")
        # the doc sub-page has the real bracket data
        doc_html = (FIXTURES_DIR / "t4127_real_jan_2026.html").read_text(encoding="utf-8")

        doc_url_fragment = "t4127-jan-payroll-deductions-formulas-computer-programs.html"

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url == t4127_mod.T4127_INDEX_URL:
                resp.text = index_html
            elif doc_url_fragment in url:
                resp.text = doc_html
            else:
                resp.text = edition_html
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.t4127.time.sleep"):
            result = t4127_mod.parse(session=session)

        assert result["tax_brackets"], "tax_brackets must not be empty"
        assert len(result["tax_brackets"]) == 5
        assert result["tax_brackets"][-1]["up_to"] is None, "top bracket up_to must be None"
        assert result["k1_rate"] == pytest.approx(0.14, abs=1e-4)


# ---------------------------------------------------------------------------
# Regression – real Jan 2026 fixture (Strategy D: caption match)
# ---------------------------------------------------------------------------

class TestRealJan2026:
    """Regression test using the real-page-modelled t4127_real_jan_2026.html fixture.

    The real T4127 computer-programs page uses table captions like
    "Table 4.1 Federal income tax rates and income thresholds".
    Strategy D (caption match) must locate the correct table directly.
    The 2026 (122nd edition) data uses 14% as the lowest federal rate.
    """

    @pytest.fixture(scope="class")
    def result(self):
        return _parse_federal(_load("t4127_real_jan_2026.html"))

    def test_bracket_count(self, result):
        assert len(result["tax_brackets"]) == 5

    def test_top_bracket_is_none(self, result):
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_k1_rate_is_14_percent(self, result):
        assert result["k1_rate"] == pytest.approx(0.14, abs=1e-4)

    def test_bpaf_has_min_and_max(self, result):
        assert "min" in result["bpaf"]
        assert "max" in result["bpaf"]
        assert result["bpaf"]["min"] > 0
        assert result["bpaf"]["max"] > 0

    def test_bpaf_max_greater_than_min(self, result):
        assert result["bpaf"]["max"] >= result["bpaf"]["min"]


# ---------------------------------------------------------------------------
# Regression – edition page has brackets; sub-page linked from it does NOT
# ---------------------------------------------------------------------------

class TestEditionHasBracketsSubpageDoesNot:
    """Regression: parse() must succeed when the edition page itself has the
    federal bracket table, even if a TOC link on that page points to a sub-page
    that does NOT contain bracket data.

    Before the fix, parse() always parsed soup_doc (the sub-page), which raised
    ValueError when the sub-page was a topic/navigation page without tables.
    The fix makes parse() try soup_edition first and only fall back to soup_doc
    when the edition has no bracket data.
    """

    def test_parse_succeeds_using_edition_page(self):
        """parse() must return valid tax_brackets from the edition page."""
        from unittest.mock import MagicMock, patch
        import cra_feed.parsers.t4127 as t4127_mod

        index_html = (FIXTURES_DIR / "t4127_index.html").read_text(encoding="utf-8")
        # Edition page has brackets AND a link to a computer-programs sub-page.
        edition_html = (
            FIXTURES_DIR / "t4127_edition_with_brackets_and_link.html"
        ).read_text(encoding="utf-8")
        # Sub-page that the TOC link resolves to — it has NO bracket data.
        subpage_html = (FIXTURES_DIR / "t4127_federal_no_table.html").read_text(
            encoding="utf-8"
        )

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url == t4127_mod.T4127_INDEX_URL:
                resp.text = index_html
            elif "computer-programs" in url:
                resp.text = subpage_html
            else:
                resp.text = edition_html
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.t4127.time.sleep"):
            result = t4127_mod.parse(session=session)

        assert result["tax_brackets"], "tax_brackets must not be empty"
        assert len(result["tax_brackets"]) == 5
        assert result["tax_brackets"][-1]["up_to"] is None, "top bracket up_to must be None"
        assert result["k1_rate"] == pytest.approx(0.15, abs=1e-4)
        assert result["bpaf"]["max"] == pytest.approx(16_129.0, abs=1.0)

    def test_parse_still_uses_subpage_when_edition_has_no_brackets(self):
        """When the edition page is a TOC (no brackets), parse() must still
        fall back to the sub-page as before.  This ensures the existing
        routing for the TOC-edition case is not broken."""
        from unittest.mock import MagicMock, patch
        import cra_feed.parsers.t4127 as t4127_mod

        index_html = (FIXTURES_DIR / "t4127_index.html").read_text(encoding="utf-8")
        # Edition page is a plain TOC with no bracket tables.
        edition_html = (FIXTURES_DIR / "t4127_edition.html").read_text(encoding="utf-8")
        # Sub-page holds the real bracket data.
        doc_html = (FIXTURES_DIR / "t4127_real_jan_2026.html").read_text(encoding="utf-8")

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url == t4127_mod.T4127_INDEX_URL:
                resp.text = index_html
            elif "computer-programs" in url:
                resp.text = doc_html
            else:
                resp.text = edition_html
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.t4127.time.sleep"):
            result = t4127_mod.parse(session=session)

        assert result["tax_brackets"], "tax_brackets must not be empty"
        assert len(result["tax_brackets"]) == 5
        assert result["tax_brackets"][-1]["up_to"] is None


# ---------------------------------------------------------------------------
# Strategy E – bulleted-list extraction (2026+ format)
# ---------------------------------------------------------------------------

class TestStyleE:
    """Strategy E: bulleted-list extraction (2026+ CRA format).

    The 2026 edition presents federal brackets as a <ul> in a "Federal Changes"
    section rather than an HTML <table>.  Strategy E must locate and parse this
    list correctly, returning the right rates and thresholds.
    """

    @pytest.fixture(scope="class")
    def result(self):
        return _parse_federal(_load("t4127_federal_brackets_styleE.html"))

    def test_bracket_count(self, result):
        assert len(result["tax_brackets"]) == 5

    def test_bracket_rates(self, result):
        expected = [0.14, 0.205, 0.26, 0.29, 0.33]
        assert [b["rate"] for b in result["tax_brackets"]] == pytest.approx(
            expected, abs=1e-4
        )

    def test_top_bracket_is_none(self, result):
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_thresholds(self, result):
        expected_up_to = [58_523.0, 117_045.0, 181_440.0, 258_482.0, None]
        actual_up_to = [b["up_to"] for b in result["tax_brackets"]]
        assert actual_up_to[:-1] == pytest.approx(expected_up_to[:-1])
        assert actual_up_to[-1] is None

    def test_bpaf_max(self, result):
        assert result["bpaf"]["max"] == pytest.approx(16_129.0, abs=1.0)

    def test_bpaf_min(self, result):
        assert result["bpaf"]["min"] == pytest.approx(14_538.0, abs=1.0)


# ---------------------------------------------------------------------------
# Regression – _find_document_url() must prefer same-directory links
# ---------------------------------------------------------------------------

class TestFindDocumentUrlLinkDisambiguation:
    """_find_document_url() must return the same-directory chapter link
    even when a legacy /tax/businesses/topics/ link appears first in the HTML.

    The fixture t4127_edition_dual_links.html has:
    - BAD (first):  /en/revenue-agency/services/tax/businesses/topics/payroll/t4127-...-computer-programs.html
    - GOOD (second): /en/revenue-agency/services/forms-publications/payroll/t4127-payroll-deductions-formulas/t4127-jan/t4127-jan-...-computer-programs.html
    """

    _EDITION_URL = (
        "https://www.canada.ca/en/revenue-agency/services/forms-publications/"
        "payroll/t4127-payroll-deductions-formulas/t4127-jan.html"
    )
    _BAD_FRAGMENT = "/tax/businesses/topics/"
    _GOOD_FRAGMENT = "t4127-jan/t4127-jan-payroll-deductions-formulas-computer-programs.html"

    @pytest.fixture(scope="class")
    def doc_url(self):
        edition_html = (FIXTURES_DIR / "t4127_edition_dual_links.html").read_text(
            encoding="utf-8"
        )
        return _find_document_url(self._EDITION_URL, edition_html)

    def test_returns_good_link_not_bad_link(self, doc_url):
        assert self._BAD_FRAGMENT not in doc_url, (
            f"_find_document_url() must NOT return the legacy topic-page URL. Got: {doc_url}"
        )

    def test_returns_same_directory_link(self, doc_url):
        assert self._GOOD_FRAGMENT in doc_url, (
            f"Expected same-directory chapter link in doc_url, got: {doc_url}"
        )

    def test_url_is_absolute(self, doc_url):
        assert doc_url.startswith("https://"), (
            f"Expected absolute URL, got: {doc_url}"
        )


# ---------------------------------------------------------------------------
# Regression – _has_t4127_content() must detect dead navigation shells
# ---------------------------------------------------------------------------

class TestHasT4127Content:
    """_has_t4127_content() must correctly classify pages."""

    def test_dead_shell_returns_false(self):
        html = (FIXTURES_DIR / "t4127_dead_nav_shell.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        assert not _has_t4127_content(soup), (
            "Dead navigation shell must not be detected as T4127 content"
        )

    def test_style_e_returns_true(self):
        html = (FIXTURES_DIR / "t4127_federal_brackets_styleE.html").read_text(
            encoding="utf-8"
        )
        soup = BeautifulSoup(html, "lxml")
        assert _has_t4127_content(soup), (
            "StyleE fixture (bulleted-list brackets + Federal Changes heading) "
            "must be detected as T4127 content"
        )

    def test_no_table_returns_false(self):
        html = (FIXTURES_DIR / "t4127_federal_no_table.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        assert not _has_t4127_content(soup), (
            "Fixture with no T4127 content must not pass content check"
        )


# ---------------------------------------------------------------------------
# End-to-end – dual-links edition, dead shell on bad URL, styleE on good URL
# ---------------------------------------------------------------------------

class TestEndToEndDualLinksDisambiguation:
    """parse() must return correct 2026 federal brackets when:
    - The edition page (t4127-jan.html) has BOTH a legacy bad link and a
      good same-directory link.
    - The bad URL returns a dead navigation shell.
    - The good URL returns the styleE bulleted-list brackets page.

    With Layer 1 fix in _find_document_url(), the bad URL should never be
    fetched.  Either way, parse() must succeed with 5 brackets at 2026 rates.
    """

    _EDITION_URL = (
        "https://www.canada.ca/en/revenue-agency/services/forms-publications/"
        "payroll/t4127-payroll-deductions-formulas/t4127-jan.html"
    )
    _BAD_FRAGMENT = "/tax/businesses/topics/"
    _BAD_URL = (
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/"
        "payroll/t4127-payroll-deductions-formulas-computer-programs.html"
    )
    _GOOD_FRAGMENT = "t4127-jan/t4127-jan-payroll-deductions-formulas-computer-programs.html"

    @pytest.fixture(scope="class")
    def result(self):
        from unittest.mock import MagicMock, patch
        import cra_feed.parsers.t4127 as t4127_mod

        index_html = (FIXTURES_DIR / "t4127_index.html").read_text(encoding="utf-8")
        edition_html = (FIXTURES_DIR / "t4127_edition_dual_links.html").read_text(
            encoding="utf-8"
        )
        dead_html = (FIXTURES_DIR / "t4127_dead_nav_shell.html").read_text(
            encoding="utf-8"
        )
        good_html = (FIXTURES_DIR / "t4127_federal_brackets_styleE.html").read_text(
            encoding="utf-8"
        )

        session = MagicMock()

        def _fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url == t4127_mod.T4127_INDEX_URL:
                resp.text = index_html
            elif self._GOOD_FRAGMENT in url:
                resp.text = good_html
            elif self._BAD_FRAGMENT in url:
                resp.text = dead_html
            else:
                resp.text = edition_html
            return resp

        session.get.side_effect = _fake_get

        with patch("cra_feed.parsers.t4127.time.sleep"):
            return t4127_mod.parse(session=session)

    def test_bracket_count(self, result):
        assert len(result["tax_brackets"]) == 5

    def test_bracket_rates(self, result):
        expected = [0.14, 0.205, 0.26, 0.29, 0.33]
        assert [b["rate"] for b in result["tax_brackets"]] == pytest.approx(
            expected, abs=1e-4
        )

    def test_top_bracket_is_none(self, result):
        assert result["tax_brackets"][-1]["up_to"] is None

    def test_thresholds(self, result):
        expected_up_to = [58_523.0, 117_045.0, 181_440.0, 258_482.0, None]
        actual_up_to = [b["up_to"] for b in result["tax_brackets"]]
        assert actual_up_to[:-1] == pytest.approx(expected_up_to[:-1])
        assert actual_up_to[-1] is None

    def test_k1_rate(self, result):
        assert result["k1_rate"] == pytest.approx(0.14, abs=1e-4)

