"""Tests for the T4127 multi-strategy federal bracket locator.

Four fixtures exercise each code path:

* styleA  – heading matches Strategy A candidate #1
            ("Federal income tax rates and income thresholds")
* styleB  – heading matches Strategy A candidate #4 ("Federal tax rates")
* styleC  – no matching heading; Strategy B (fingerprint) must succeed
* no_table – no bracket table at all; ValueError must be raised with the
             source URL and --debug-html hint in the message
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from cra_feed.parsers.t4127 import _parse_federal

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
