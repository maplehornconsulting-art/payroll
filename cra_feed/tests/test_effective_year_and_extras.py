"""Year selection for CPP/EI rows, and the amounts read outside the bracket
tables (maximums, CEA, tax reductions, CPP base rate)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from cra_feed import scraper
from cra_feed.parsers import cpp_ei, t4127
from cra_feed.validate import validate_feed

# Shaped like the live CRA pages in November: next year's row is already
# published ("New 2027") above the current year's.
CPP_HTML = """
<table><caption>CPP contribution rates, maximums and exemptions</caption>
<tr><th>Year</th><th>Maximum annual pensionable earnings</th>
<th>Basic exemption amount</th><th>Maximum contributory earnings</th>
<th>Employee and employer contribution rate (%)</th>
<th>Maximum annual employee and employer contribution</th>
<th>Maximum annual self-employed contribution</th></tr>
<tr><th><span>New</span> 2027</th><td>$76,700</td><td>$3,500</td><td>$73,200</td>
<td>5.75</td><td>$4,209.00</td><td>$8,418.00</td></tr>
<tr><th>2026</th><td>$74,600</td><td>$3,500</td><td>$71,100</td>
<td>5.95</td><td>$4,230.45</td><td>$8,460.90</td></tr>
</table>"""

CPP2_HTML = """
<table><caption>CPP2 contribution rates and maximums</caption>
<tr><th>Year</th><th>Additional maximum annual pensionable earnings</th>
<th>Employee and employer contribution rate (%)</th>
<th>Maximum annual employee and employer contribution</th>
<th>Maximum annual self-employed contribution</th></tr>
<tr><th>New 2027</th><td>$87,400</td><td>4%</td><td>$428</td><td>$856</td></tr>
<tr><th>2026</th><td>$85,000</td><td>4%</td><td>$416</td><td>$832</td></tr>
</table>"""

EI_HTML = """
<table><caption>Federal EI premium rates and maximums</caption>
<tr><th>Year</th><th>Maximum annual insurable earnings</th><th>Rate (%)</th>
<th>Maximum annual employee premium</th><th>Maximum annual employer premium</th></tr>
<tr><th>New 2027</th><td>$70,800</td><td>1.64</td><td>$1,161.12</td><td>$1,625.57</td></tr>
<tr><th>2026</th><td>$68,900</td><td>1.63</td><td>$1,123.07</td><td>$1,572.30</td></tr>
</table>
<table><caption>Quebec EI premium rates and maximums</caption>
<tr><th>Year</th><th>Maximum annual insurable earnings</th><th>Rate (%)</th>
<th>Maximum annual employee premium</th><th>Maximum annual employer premium</th></tr>
<tr><th>New 2027</th><td>$70,800</td><td>1.29</td><td>$913.32</td><td>$1,278.65</td></tr>
</table>"""

T4127_HTML = """
<p>British Columbia</p>
<p>S = Where A ≤ $25,570, S is equal to the lesser of: (i) T4; (ii) $690</p>
<p>= Where $25,570 &lt; A ≤ $44,952, S is equal to the lesser of:
(i) T4; (ii) $690 – [(A – $25,570) × 3.56%]</p>
<p>= Where A &gt; $44,952 = $0</p>
<table><caption>Table 8.2 Other rates and amounts for 2027</caption>
<tr><th></th><th>Basic amount</th><th>Index rate</th><th>LCP rate</th><th>LCP amount</th>
<th>CEA</th><th>S2</th><th>T4 to V1</th><th>V1 rate</th><th>Abatement</th><th>Surtax</th></tr>
<tr><th>Federal</th><td>BPAF</td><td>0.026</td><td>0.150</td><td>750</td><td>1,540</td>
<td></td><td></td><td></td><td></td><td></td></tr>
<tr><th>BC</th><td>13,216</td><td>-</td><td></td><td></td><td></td><td>690</td>
<td></td><td></td><td></td><td></td></tr>
<tr><th>ON</th><td>13,261</td><td>0.021</td><td></td><td></td><td></td><td>306</td>
<td>0</td><td>0</td><td></td><td></td></tr>
<tr><td>5,940</td><td>0.20</td><td></td><td></td></tr>
<tr><th>YT</th><td>BPAYT</td><td>0.026</td><td></td><td></td><td>1,540</td><td></td>
<td></td><td></td><td></td><td></td></tr>
</table>
<table><caption>Table 8.4 Base Canada Pension Plan / Quebec Pension Plan 2027 rates and amounts</caption>
<tr><th>CPP/QPP</th><th>Year's Maximum Pensionable Earnings (YMPE)</th>
<th>Base Employee and Employer Contribution Rate</th>
<th>Maximum Base Employee and Employer Contribution</th></tr>
<tr><th>CPP (Canada except QC)</th><td>76,700.00</td><td>0.0475</td><td>3,477.00</td></tr>
<tr><th>QPP (QC)</th><td>76,700.00</td><td>0.0530</td><td>3,879.60</td></tr>
</table>
<table><caption>Table 8.23 Other rates and amounts for 2026</caption>
<tr><th></th><th>Basic amount</th><th>Index rate</th><th>LCP rate</th><th>LCP amount</th>
<th>CEA</th><th>S2</th></tr>
<tr><th>Federal</th><td>BPAF</td><td>0.020</td><td>0.150</td><td>750</td><td>1,501</td><td></td></tr>
<tr><th>BC</th><td>13,216</td><td>0.022</td><td></td><td></td><td></td><td>575</td></tr>
</table>
<table><caption>Table 8.25 Base Canada Pension Plan / Quebec Pension Plan 2026 rates and amounts</caption>
<tr><th>CPP/QPP</th><th>YMPE</th><th>Base Employee and Employer Contribution Rate</th></tr>
<tr><th>CPP (Canada except QC)</th><td>74,600.00</td><td>0.0495</td></tr>
</table>"""


def _soup(html: str = T4127_HTML) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class TestEffectiveYearRows:
    """The row read is the effective year's, whatever today's date is."""

    def test_requested_year_wins_over_today(self):
        # Scraper run in November 2026 for the January 2027 edition.
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = cpp_ei._parse_cpp_page(CPP_HTML, 2027)
            cpp2 = cpp_ei._parse_cpp2_page(CPP2_HTML, 2027)
            ei = cpp_ei._parse_ei_page(EI_HTML, 2027)
        assert cpp == {
            "rate": 0.0575, "ympe": 76700, "basic_exemption": 3500,
            "max_contribution": 4209.0,
        }
        assert cpp2 == {"rate": 0.04, "yampe": 87400, "max_contribution": 428.0}
        assert ei == {
            "rate": 0.0164, "max_insurable_earnings": 70800, "max_premium": 1161.12,
        }

    def test_defaults_to_today_when_no_year_given(self):
        with patch("cra_feed.parsers.cpp_ei._current_year", return_value=2026):
            cpp, _ = cpp_ei._parse_cpp_page(CPP_HTML)
            ei = cpp_ei._parse_ei_page(EI_HTML)
        assert (cpp["ympe"], cpp["rate"], cpp["max_contribution"]) == (74600, 0.0595, 4230.45)
        assert (ei["max_insurable_earnings"], ei["rate"]) == (68900, 0.0163)

    def test_rates_are_exact_decimals(self):
        cpp, _ = cpp_ei._parse_cpp_page(CPP_HTML, 2026)
        ei = cpp_ei._parse_ei_page(EI_HTML, 2027)
        assert repr(cpp["rate"]) == "0.0595"
        assert repr(ei["rate"]) == "0.0164"

    def test_year_not_published_yet_aborts(self):
        """No row for the effective year must fail, never fall back to another year."""
        pages = {
            cpp_ei.CPP_SOURCE_URL: CPP_HTML,
            cpp_ei.CPP2_SOURCE_URL: CPP2_HTML,
            cpp_ei.EI_SOURCE_URL: EI_HTML,
        }
        with patch("cra_feed.parsers.cpp_ei._fetch", side_effect=lambda s, url: pages[url]):
            with pytest.raises(ValueError, match="2028"):
                cpp_ei.parse(object(), year=2028)
            assert cpp_ei.parse(object(), year=2027)["cpp"]["ympe"] == 76700


class TestOtherAmounts:
    def test_cea_and_s2_come_from_the_current_year_table(self):
        other = t4127._parse_other_amounts(_soup())
        assert other == {"cea": 1540.0, "s2": {"BC": 690.0, "ON": 306.0}}

    def test_missing_table_yields_nothing(self):
        assert t4127._parse_other_amounts(_soup("<p>delta edition</p>")) == {
            "cea": None, "s2": {},
        }

    def test_bc_reduction(self):
        assert t4127._parse_bc_reduction(_soup(), 690.0) == {
            "base": 690.0, "phase_from": 25570.0, "phase_to": 44952.0, "rate": 0.0356,
        }

    def test_bc_reduction_absent(self):
        assert t4127._parse_bc_reduction(_soup("<p>Ontario V1 = ...</p>")) is None

    def test_bc_reduction_rejected_when_it_disagrees_with_table(self):
        assert t4127._parse_bc_reduction(_soup(), 575.0) is None

    def test_cpp_base_rate_is_the_current_year_cpp_row(self):
        assert t4127._parse_cpp_base_rate(_soup()) == 0.0475

    def test_cpp_base_rate_absent(self):
        assert t4127._parse_cpp_base_rate(_soup("<p>nothing</p>")) is None


class TestFeedOutput:
    _T4127 = {
        "effective_date": "2027-01-01",
        "source_urls": ["https://www.canada.ca/t4127"],
        "bpaf": {"min": 15214.0, "max": 16879.0},
        "k1_rate": 0.14,
        "tax_brackets": [{"up_to": 60044.0, "rate": 0.14}, {"up_to": None, "rate": 0.33}],
        "cea": 1540.0,
        "cpp_base_rate": 0.0475,
        "provinces": {
            "BC": {
                "bpa": 13216.0,
                "tax_brackets": [{"up_to": 50363.0, "rate": 0.056}, {"up_to": None, "rate": 0.205}],
                "surtax": [],
                "reduction": {"base": 690.0, "phase_from": 25570.0, "phase_to": 44952.0, "rate": 0.0356},
            },
            "ON": {
                "bpa": 13261.0,
                "tax_brackets": [{"up_to": 55023.0, "rate": 0.0505}, {"up_to": None, "rate": 0.1316}],
                "surtax": [[5940.0, 0.2]],
                "reduction_base": 306.0,
            },
            "AB": {
                "bpa": 23225.0,
                "tax_brackets": [{"up_to": 62424.0, "rate": 0.08}, {"up_to": None, "rate": 0.15}],
            },
        },
    }
    _CPP_EI = {
        "cpp": {"rate": 0.0575, "ympe": 76700, "basic_exemption": 3500, "max_contribution": 4209.0},
        "cpp2": {"rate": 0.04, "yampe": 87400, "max_contribution": 428.0},
        "ei": {"rate": 0.0164, "max_insurable_earnings": 70800, "max_premium": 1161.12},
        "source_urls": ["https://www.canada.ca/cpp"],
    }

    def _build(self, t4127_data=None, cpp_ei_data=None):
        with patch.object(scraper.t4127, "parse", return_value=t4127_data or self._T4127), \
             patch.object(scraper.cpp_ei, "parse", return_value=cpp_ei_data or self._CPP_EI) as cpp_parse:
            feed = scraper.build_feed()
        return feed, cpp_parse

    def test_cpp_ei_is_asked_for_the_effective_year(self):
        _, cpp_parse = self._build()
        assert cpp_parse.call_args.kwargs["year"] == 2027

    def test_new_fields_are_published_and_valid(self):
        feed, _ = self._build()
        d = scraper.feed_to_dict(feed)
        validate_feed(d)
        assert d["federal"]["cea"] == 1540.0
        assert d["cpp"]["max_contribution"] == 4209.0 and d["cpp"]["base_rate"] == 0.0475
        assert d["cpp2"]["max_contribution"] == 428.0
        assert d["ei"]["max_premium"] == 1161.12
        assert d["provinces"]["BC"]["reduction"]["base"] == 690.0
        assert d["provinces"]["ON"]["reduction_base"] == 306.0
        assert "reduction" not in d["provinces"]["AB"]
        assert "reduction_base" not in d["provinces"]["AB"]
        assert "k1p" not in d["provinces"]["AB"]

    def test_checksum_covers_exactly_what_is_published(self):
        feed, _ = self._build()
        d = scraper.feed_to_dict(feed)
        assert scraper._canonical_checksum(d) == d["checksum_sha256"]

    def test_missing_optionals_are_omitted_not_null(self):
        t = {**self._T4127, "cea": None, "cpp_base_rate": None}
        c = {
            "cpp": {"rate": 0.0575, "ympe": 76700, "basic_exemption": 3500},
            "cpp2": {"rate": 0.04, "yampe": 87400},
            "ei": {"rate": 0.0164, "max_insurable_earnings": 70800},
            "source_urls": ["https://www.canada.ca/cpp"],
        }
        feed, _ = self._build(t, c)
        d = scraper.feed_to_dict(feed)
        validate_feed(d)
        assert "cea" not in d["federal"]
        assert set(d["cpp"]) == {"rate", "ympe", "basic_exemption"}
        assert set(d["cpp2"]) == {"rate", "yampe"}
        assert set(d["ei"]) == {"rate", "max_insurable_earnings"}
        assert scraper._canonical_checksum(d) == d["checksum_sha256"]
        # the open-ended top bracket must stay an explicit null
        assert d["federal"]["tax_brackets"][-1]["up_to"] is None
