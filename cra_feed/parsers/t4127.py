"""Real parser for the CRA T4127 Payroll Deductions Formulas publication.

Fetches the T4127 index page, discovers the current HTML edition URL, and
parses federal income tax brackets, BPAF, K1 rate, effective date, and
all provincial/territorial tax data (excluding Quebec).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from urllib.parse import urljoin

import requests as _requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

T4127_INDEX_URL = (
    "https://www.canada.ca/en/revenue-agency/services/forms-publications/"
    "payroll/t4127-payroll-deductions-formulas.html"
)

PROVINCE_NAME_TO_CODE: dict[str, str] = {
    "alberta": "AB",
    "british columbia": "BC",
    "manitoba": "MB",
    "new brunswick": "NB",
    "newfoundland and labrador": "NL",
    "newfoundland": "NL",
    "nova scotia": "NS",
    "northwest territories": "NT",
    "nunavut": "NU",
    "ontario": "ON",
    "prince edward island": "PE",
    "saskatchewan": "SK",
    "yukon": "YT",
}

PROVINCES_IN_SCOPE = sorted(PROVINCE_NAME_TO_CODE.values())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_num(s: str) -> float:
    """Strip dollar signs, commas, percent signs and return float."""
    cleaned = s.strip().replace(",", "").replace("$", "").replace("%", "").strip()
    return float(cleaned)


def _fetch(session, url: str) -> str:
    """GET *url* and return HTML text, sleeping 1 s afterwards (polite)."""
    logger.info("Fetching %s", url)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    time.sleep(1)
    return resp.text


def _find_edition_url(index_html: str) -> str:
    """Return the URL of the current T4127 HTML edition from the index page."""
    soup = BeautifulSoup(index_html, "lxml")

    jan_candidates: list[str] = []
    jul_candidates: list[str] = []

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        # Skip PDFs and anything that isn't HTML
        if href.lower().endswith(".pdf"):
            continue
        href_l = href.lower()
        if "t4127" not in href_l:
            continue
        if "jan" in href_l:
            jan_candidates.append(href)
        elif "jul" in href_l:
            jul_candidates.append(href)

    # Prefer the JAN edition (most current for a given calendar year)
    chosen: str | None = None
    for href in jan_candidates + jul_candidates:
        chosen = href
        break

    if chosen is None:
        raise ValueError(
            "Could not find a T4127 HTML edition link on the index page. "
            f"Index URL: {T4127_INDEX_URL}"
        )

    return urljoin(T4127_INDEX_URL, chosen)


def _find_document_url(edition_url: str, edition_html: str) -> str:
    """
    From an edition landing page, find the URL of the actual formulas document.

    If the edition page already contains bracket-like tables, it IS the
    document.  Otherwise follow the first 'computer-programs' or 'formulas'
    link to the deeper sub-page that holds the actual tax data.

    Note: the old heuristic of checking for text keywords like "taxable income"
    was too broad — TOC pages often include those words in link text, causing a
    false early-return.  We now require an actual scoring-positive table.
    """
    soup = BeautifulSoup(edition_html, "lxml")

    # If the page already has a bracket-like table, it is itself the document
    for table in soup.find_all("table"):
        if _score_bracket_table(table) >= 2:
            return edition_url

    # No bracket tables found — look for a linked sub-page
    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_l = href.lower()
        if href_l.endswith(".pdf"):
            continue
        if "computer-programs" in href_l or (
            "t4127" in href_l and "formulas" in href_l and href_l.endswith(".html")
        ):
            return urljoin(edition_url, href)

    # Fall back: the edition page itself is the document
    return edition_url


def _parse_effective_date(soup: BeautifulSoup) -> str | None:
    """Extract the effective date from various locations in the T4127 HTML."""
    month_pattern = (
        r"(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)"
    )
    date_re = re.compile(
        rf"effective\s+({month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})",
        re.I,
    )

    # 1. Page title
    title = soup.find("title")
    if title:
        m = date_re.search(title.get_text())
        if m:
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass

    # 2. Headings and paragraphs near the top of the page
    for tag in soup.find_all(["h1", "h2", "h3", "p"])[:30]:
        m = date_re.search(tag.get_text())
        if m:
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass

    return None


# ---------------------------------------------------------------------------
# Tax table parsing
# ---------------------------------------------------------------------------

def _parse_bracket_table(table) -> list[dict]:
    """
    Parse an HTML tax-bracket table into a list of ``{up_to, rate}`` dicts.

    Handles column formats like:
      "Annual net income (A)" | "Rate (R)" | [optional constant columns]
    Income text examples:
      "$0 to $57,375"
      "$57,376 to $114,750"
      "Over $220,000"
      "More than $258,482"
      "0.00 – 57,375.00"
    Rate text examples:
      "15%", "20.5%", "0.15", "0.205"
    """
    brackets: list[dict] = []

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # Skip header rows entirely
        if all(c.name == "th" for c in cells):
            continue

        texts = [c.get_text(" ", strip=True) for c in cells]
        income_text = texts[0]

        # Identify rate column: first cell whose text matches a rate pattern
        rate_text: str | None = None
        for t in texts[1:]:
            t_stripped = t.strip()
            if re.search(r"\d+\.?\d*\s*%", t_stripped):
                rate_text = t_stripped
                break
            # Decimal fraction like "0.15" or "0.0595"
            if re.match(r"^0\.\d+$", t_stripped):
                rate_text = t_stripped
                break

        if rate_text is None:
            continue

        # Parse rate
        try:
            rate_val = _parse_num(rate_text)
            if rate_val > 1:  # percentage notation (e.g. 15.0 → 0.15)
                rate_val = rate_val / 100.0
        except ValueError:
            continue

        # Determine upper bound
        income_l = income_text.lower()
        top_bracket_markers = ("over", "more than", "above", "and over", "et plus", "exceeds")
        if any(m in income_l for m in top_bracket_markers):
            up_to = None
        else:
            # Extract all numeric values from the income cell
            raw_nums = re.findall(r"[\d,]+(?:\.\d+)?", income_text)
            clean_nums: list[float] = []
            for n in raw_nums:
                try:
                    clean_nums.append(float(n.replace(",", "")))
                except ValueError:
                    continue
            if len(clean_nums) >= 2:
                # The upper bound is the LARGER of the two numbers (or the last)
                up_to = max(clean_nums)
            elif len(clean_nums) == 1:
                up_to = clean_nums[0]
            else:
                # No parseable number; skip this row
                continue

        brackets.append({"up_to": up_to, "rate": rate_val})

    return brackets


def _score_bracket_table(table) -> int:
    """
    Score a table on how tax-bracket-like it is.

    Returns an integer 0–3:
      +1  header row contains "rate" AND one of "threshold"/"income"/"bracket"
      +1  at least 4 non-header data rows
      +1  at least 4 data rows each having ≥2 numeric-looking cells
          (a large number like an income threshold, or a percentage)
    """
    rows = table.find_all("tr")
    if not rows:
        return 0

    header_cells = rows[0].find_all(["th", "td"])
    header_text = " ".join(c.get_text(" ", strip=True).lower() for c in header_cells)

    score = 0
    if "rate" in header_text and any(
        w in header_text for w in ("threshold", "income", "bracket")
    ):
        score += 1

    data_rows = [
        row
        for row in rows[1:]
        if row.find_all(["td", "th"])
        and not all(c.name == "th" for c in row.find_all(["td", "th"]))
    ]
    if len(data_rows) >= 4:
        score += 1

    def _cell_numeric(cell_text: str) -> bool:
        return bool(
            re.search(r"\d+\.?\d*\s*%", cell_text)
            or re.search(r"[\d,]{4,}", cell_text)
        )

    numeric_rows = sum(
        1
        for row in data_rows
        if sum(
            1
            for c in row.find_all(["td", "th"])
            if _cell_numeric(c.get_text(strip=True))
        )
        >= 2
    )
    if numeric_rows >= 4:
        score += 1

    return score


def _find_table_after_heading_or_fingerprint(
    soup: BeautifulSoup,
    heading_candidates: list,
    fingerprint_fn,
    anchor_tokens: list | None = None,
) -> tuple:
    """
    Locate a tax bracket table using four strategies, in order:

    Strategy A — Phrase match in block headings (h1–h4):
        Iterate ``heading_candidates`` (case-insensitive, whitespace-normalised).
        For the first heading whose text *contains* the candidate phrase, take
        the first ``<table>`` that follows it (stopping at the next ``<h2>``).

    Strategy D — Table caption match:
        For each ``<table>``, check whether its ``<caption>`` contains any of
        the candidate phrases.  Return the table directly (not the *next* table
        after the caption — that would be wrong).  Tried before B/C so that an
        explicit CRA caption like "Table 4.1 Federal income tax rates and income
        thresholds" is preferred over fingerprint guessing.

    Strategy B — Fingerprint scoring:
        Score every ``<table>`` with ``fingerprint_fn``; accept the table with
        the highest score if it is ≥ 3.  Ties are broken in document order
        (first occurrence wins).

    Strategy C — Text anchor:
        Search for any of ``anchor_tokens`` as literal text; walk up to the
        nearest ``<table>`` ancestor.

    Returns ``(table_tag, strategy_letter, heading_text_or_token)``
    or ``(None, None, None)`` if all strategies fail.
    """
    # Strategy A — heading h1–h4 immediately preceding the table
    for candidate in heading_candidates:
        candidate_l = candidate.lower()
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            heading_text = " ".join(heading.get_text().split())
            if candidate_l in heading_text.lower():
                for sibling in heading.find_all_next():
                    if sibling.name == "table":
                        return sibling, "A", heading_text
                    if sibling.name in ("h1", "h2") and sibling is not heading:
                        break

    # Strategy D — table with a caption that contains a known phrase
    for candidate in heading_candidates:
        candidate_l = candidate.lower()
        for table in soup.find_all("table"):
            cap = table.find("caption")
            if cap:
                cap_text = " ".join(cap.get_text().split())
                if candidate_l in cap_text.lower():
                    return table, "D", cap_text

    # Strategy B — fingerprint scoring
    best_table = None
    best_score = 0
    for table in soup.find_all("table"):
        s = fingerprint_fn(table)
        if s > best_score:
            best_score = s
            best_table = table

    if best_score >= 3 and best_table is not None:
        return best_table, "B", ""

    # Strategy C — text anchor
    if anchor_tokens:
        for token in anchor_tokens:
            for text_node in soup.find_all(string=re.compile(re.escape(token))):
                ancestor = text_node.find_parent("table")
                if ancestor is not None:
                    return ancestor, "C", token

    return None, None, None


# ---------------------------------------------------------------------------
# Federal section constants
# ---------------------------------------------------------------------------

_FEDERAL_HEADING_CANDIDATES = [
    "Federal income tax rates and income thresholds",
    "Federal income tax brackets",
    "Federal tax rates and income thresholds",
    "Federal tax rates",
    "Federal tax",
]

_FEDERAL_ANCHOR_TOKENS = ["$15,000", "5.05%"]

# Regex for the 2026+ bulleted-list bracket format, e.g.:
#   "for income under $58,523, the tax rate is 14%"
#   "for income from $58,523 to $117,045, the tax rate is 20.5%"
#   "for income of $258,482 and over, the tax rate is 33%"
_UL_BRACKET_RE = re.compile(
    r"^for income "
    r"(?:under \$([\d,]+),|from \$([\d,]+) to \$([\d,]+),|of \$([\d,]+) and over,)"
    r" the tax rate is ([\d.]+)%",
    re.I,
)


def _parse_ul_bracket_items(ul) -> list[dict]:
    """Parse federal bracket items from a <ul> or <ol> element (2026+ format)."""
    brackets: list[dict] = []
    for li in ul.find_all("li", recursive=False):
        text = " ".join(li.get_text().split())
        m = _UL_BRACKET_RE.match(text)
        if not m:
            continue
        under_thresh, from_low, from_high, over_thresh, rate_str = m.groups()
        rate = float(rate_str) / 100.0
        if under_thresh is not None:
            up_to: float | None = float(under_thresh.replace(",", ""))
        elif from_high is not None:
            up_to = float(from_high.replace(",", ""))
        elif over_thresh is not None:
            up_to = None
        else:
            continue
        brackets.append({"up_to": up_to, "rate": rate})
    return brackets


def _parse_brackets_from_ul(soup: BeautifulSoup) -> list[dict]:
    """
    Strategy E: parse federal tax brackets from a bulleted list (2026+ format).

    Primary: find a paragraph whose text contains "tax rates" and
    "as follows", then take the next <ul> or <ol>.

    Secondary (fallback): scan all <ul>/<ol> for lists whose items all match
    the bracket pattern; accept if at least 4 items match.
    """
    # Primary: look for the lead-in sentence, then take the next <ul>/<ol>
    for p in soup.find_all(["p", "li", "div"]):
        text = " ".join(p.get_text().split()).lower()
        if "tax rates" in text and "as follows" in text:
            for sib in p.find_all_next():
                if sib.name in ("ul", "ol"):
                    brackets = _parse_ul_bracket_items(sib)
                    if brackets:
                        return brackets
                    break
                if sib.name in ("h1", "h2", "h3"):
                    break

    # Secondary: scan all <ul>/<ol> for at least 4 bracket-like items
    for ul in soup.find_all(["ul", "ol"]):
        brackets = _parse_ul_bracket_items(ul)
        if len(brackets) >= 4:
            return brackets

    return []


# ---------------------------------------------------------------------------
# Federal section
# ---------------------------------------------------------------------------

def _parse_federal(soup: BeautifulSoup, source_url: str = "") -> dict:
    """
    Extract federal income tax brackets, BPAF min/max, and K1 rate.

    Uses multiple strategies so minor changes to canada.ca HTML layout do
    not cause hard failures:

    * Strategy E – bulleted-list extraction (2026+ format).
    * Strategy A – find a known heading phrase, take the first table after it.
    * Strategy D – table caption match.
    * Strategy B – score all tables by how bracket-table-like they look; accept
      the highest-scoring one (minimum score 3).
    * Strategy C – anchor on a known dollar/rate token and walk up to a table.

    Returns::

        {
            "tax_brackets": [...],
            "bpaf": {"min": float, "max": float},
            "k1_rate": float,
        }
    """
    # Strategy E — bulleted list (2026+ format)
    brackets_ul = _parse_brackets_from_ul(soup)
    if brackets_ul:
        logger.info("Federal brackets located via Strategy E (bulleted list)")
        k1_rate = brackets_ul[0]["rate"]
        bpaf = _parse_bpaf(soup, k1_rate)
        return {"tax_brackets": brackets_ul, "bpaf": bpaf, "k1_rate": k1_rate}

    table, strategy, heading_text = _find_table_after_heading_or_fingerprint(
        soup,
        _FEDERAL_HEADING_CANDIDATES,
        _score_bracket_table,
        _FEDERAL_ANCHOR_TOKENS,
    )

    if table is None:
        url_hint = f" (source URL: {source_url})" if source_url else ""
        raise ValueError(
            f"Could not locate federal tax bracket table in T4127 HTML{url_hint}. "
            "Re-run with --debug-html to save the fetched HTML for inspection."
        )

    logger.info(
        "Federal brackets located via strategy %s (heading=%r)",
        strategy,
        heading_text,
    )

    brackets = _parse_bracket_table(table)
    if not brackets:
        raise ValueError("Federal tax bracket table found but parsed 0 brackets")

    k1_rate = brackets[0]["rate"]  # lowest rate = K1

    # --- BPAF ---
    bpaf = _parse_bpaf(soup, k1_rate)

    return {"tax_brackets": brackets, "bpaf": bpaf, "k1_rate": k1_rate}


def _parse_bpaf(soup: BeautifulSoup, k1_rate: float) -> dict:
    """
    Extract BPAF maximum and minimum from the T4127 HTML.

    The BPAF section may appear as a table or as prose text.  We look for
    dollar amounts adjacent to the words "maximum" / "minimum", constrained to
    the BPA plausible range ($5,000–$30,000) to avoid picking up income
    thresholds that appear in the same paragraph.
    """
    BPA_MIN_PLAUSIBLE = 5_000.0
    BPA_MAX_PLAUSIBLE = 30_000.0

    def _is_bpa(v: float) -> bool:
        return BPA_MIN_PLAUSIBLE <= v <= BPA_MAX_PLAUSIBLE

    # Strategy 1: dedicated BPAF / BPA table
    for t in soup.find_all("table"):
        cap = t.find("caption")
        if cap:
            cap_text = cap.get_text().lower()
            if "bpa" in cap_text or "basic personal" in cap_text:
                amounts = []
                for row in t.find_all("tr"):
                    for cell in row.find_all(["td", "th"]):
                        txt = cell.get_text(strip=True)
                        m = re.search(r"([\d,]+\.?\d*)", txt.replace(",", ""))
                        if m:
                            try:
                                v = float(m.group().replace(",", ""))
                                if _is_bpa(v):
                                    amounts.append(v)
                            except ValueError:
                                pass
                if len(amounts) >= 2:
                    return {"max": max(amounts), "min": min(amounts)}

    # Strategy 2: look for dollar amounts immediately following "maximum" or
    # "minimum" keywords within the BPA section.
    max_bpa: float | None = None
    min_bpa: float | None = None

    # Pattern: "maximum ... $16,452" or "$16,452 ... maximum"
    for tag in soup.find_all(["p", "li", "td", "dd"]):
        text = tag.get_text(" ", strip=True)
        text_l = text.lower()
        if "basic personal" not in text_l and "bpa" not in text_l:
            continue

        # Extract all dollar amounts in BPA range from this element
        amounts_in_tag = []
        for m in re.finditer(r"\$([\d,]+(?:\.\d+)?)", text):
            try:
                v = float(m.group(1).replace(",", ""))
                if _is_bpa(v):
                    amounts_in_tag.append(v)
            except ValueError:
                pass

        if not amounts_in_tag:
            continue

        # Associate each amount with the nearest "maximum" / "minimum" keyword
        for amount in amounts_in_tag:
            amount_pos = text.find(f"${amount:,.2f}")
            if amount_pos < 0:
                # Try without decimals
                amount_pos = text.find(f"${amount:,.0f}")
            if amount_pos < 0:
                continue

            before = text_l[max(0, amount_pos - 80): amount_pos]
            after = text_l[amount_pos: amount_pos + 80]

            if "maximum" in before or "maximum" in after:
                if max_bpa is None or amount > max_bpa:
                    max_bpa = amount
            if "minimum" in before or "minimum" in after:
                if min_bpa is None or amount < min_bpa:
                    min_bpa = amount

    if max_bpa is not None and min_bpa is not None:
        return {"max": max_bpa, "min": min_bpa}
    if max_bpa is not None:
        # Only maximum found: minimum defaults to maximum (no phase-out)
        return {"max": max_bpa, "min": max_bpa}

    # Strategy 3: fall back — collect all plausible BPA amounts in the page
    # and take the two distinct extremes (if there are two)
    all_amounts = set()
    for m in re.finditer(r"\$([\d,]+(?:\.\d+)?)", soup.get_text(" ")):
        try:
            v = float(m.group(1).replace(",", ""))
            if _is_bpa(v):
                all_amounts.add(round(v, 2))
        except ValueError:
            pass

    if len(all_amounts) >= 2:
        sorted_amounts = sorted(all_amounts)
        # The two we want are most likely the maximum and minimum BPA
        # (other amounts in range may exist, but the BPA pair is typically close)
        return {"max": sorted_amounts[-1], "min": sorted_amounts[0]}
    if len(all_amounts) == 1:
        v = all_amounts.pop()
        return {"max": v, "min": v}

    logger.warning(
        "Could not parse BPAF from T4127 HTML — no BPA dollar amounts found in the "
        "plausible range ($%.0f–$%.0f). The T4127 document structure may have changed.",
        BPA_MIN_PLAUSIBLE,
        BPA_MAX_PLAUSIBLE,
    )
    raise ValueError("Could not parse BPAF (basic personal amount) from T4127 HTML")


# ---------------------------------------------------------------------------
# Provincial sections
# ---------------------------------------------------------------------------

def _parse_provinces(soup: BeautifulSoup) -> dict[str, dict]:
    """
    Parse all in-scope provincial/territorial tax data from the T4127 HTML.

    Returns a dict keyed by 2-letter province code with values::

        {"bpa": float, "tax_brackets": [...]}
    """
    provinces: dict[str, dict] = {}

    for prov_name, code in PROVINCE_NAME_TO_CODE.items():
        try:
            prov_data = _parse_one_province(soup, prov_name, code)
            if prov_data:
                provinces[code] = prov_data
        except Exception as exc:
            logger.warning("Could not parse province %s (%s): %s", code, prov_name, exc)

    return provinces


def _parse_one_province(soup: BeautifulSoup, prov_name: str, code: str) -> dict | None:
    """Parse tax bracket table and BPA for a single province/territory."""
    # Find the heading for this province
    prov_heading = None
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        htext = heading.get_text(" ", strip=True).lower()
        if prov_name in htext:
            prov_heading = heading
            break

    if prov_heading is None:
        return None

    # Collect HTML between this heading and the next same/higher-level heading
    heading_level = int(prov_heading.name[1])
    section_tags = []
    for sibling in prov_heading.find_all_next():
        if sibling.name and sibling.name[0] == "h":
            sib_level = int(sibling.name[1])
            if sib_level <= heading_level:
                break
        section_tags.append(sibling)

    # Build a mini-soup from the section
    section_html = "".join(str(t) for t in section_tags)
    section_soup = BeautifulSoup(f"<div>{section_html}</div>", "lxml")

    # --- Tax brackets ---
    # Build province-specific heading candidates for Strategy A
    prov_heading_candidates = [
        f"{prov_name} provincial tax rates and income thresholds",
        f"{prov_name} provincial tax rates",
        f"{prov_name} provincial tax",
        f"{prov_name} income tax rates",
        f"{prov_name} tax rates",
        "provincial tax rates and income thresholds",
        "provincial tax rates",
        "provincial income tax rates",
        "tax rates",
    ]
    table, _strategy, _heading = _find_table_after_heading_or_fingerprint(
        section_soup,
        prov_heading_candidates,
        _score_bracket_table,
    )

    brackets: list[dict] = []
    if table is not None:
        brackets = _parse_bracket_table(table)

    # Fallback: scan all tables in the section (preserves original behaviour)
    if not brackets:
        for t in section_soup.find_all("table"):
            parsed = _parse_bracket_table(t)
            if parsed:
                brackets = parsed
                break

    if not brackets:
        return None

    # --- BPA ---
    bpa = _parse_province_bpa(section_soup, prov_name)

    return {"bpa": bpa, "tax_brackets": brackets}


def _parse_province_bpa(section_soup, prov_name: str) -> float:
    """
    Extract the provincial Basic Personal Amount from a province's HTML section.

    Looks for dollar amounts associated with keywords "basic personal" or "BPA".
    Falls back to the largest dollar amount in the section.
    """
    text = section_soup.get_text(" ")

    # Prefer amounts explicitly labeled as BPA / basic personal amount
    bpa_re = re.compile(r"(?:basic\s+personal\s+amount|bpa)[^$\d]{0,60}\$([\d,]+(?:\.\d+)?)", re.I)
    m = bpa_re.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # Alternative: "$X,XXX" near "basic personal" in reverse order
    bpa_rev_re = re.compile(r"\$([\d,]+(?:\.\d+)?)[^$\d]{0,60}(?:basic\s+personal\s+amount|bpa)", re.I)
    m = bpa_rev_re.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # Fall back: largest plausible dollar amount in the section
    amounts = re.findall(r"\$([\d,]+(?:\.\d+)?)", text)
    plausible = []
    for a in amounts:
        try:
            v = float(a.replace(",", ""))
            if 5_000 < v < 50_000:  # plausible BPA range
                plausible.append(v)
        except ValueError:
            pass

    if plausible:
        return max(plausible)

    logger.warning("Could not parse BPA for province %s; defaulting to 0.0", prov_name)
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(session=None, debug_dir=None) -> dict:
    """
    Fetch and parse the CRA T4127 Payroll Deductions Formulas publication.

    Parameters
    ----------
    session:
        Optional ``requests.Session`` (a new one is created when not supplied).
    debug_dir:
        Optional directory path.  When provided and a parser exception occurs,
        the raw fetched HTML is written to ``<debug_dir>/t4127.html`` so the
        failure can be inspected without re-running the scraper.

    Returns a dict with keys:
      - bpaf: {"min": float, "max": float}
      - k1_rate: float
      - tax_brackets: list[{"up_to": float|None, "rate": float}]
      - effective_date: str  (ISO date, e.g. "2026-01-01")
      - source_url: str
      - provinces: dict[str, {"bpa": float, "tax_brackets": [...]}]
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

    # 1. Fetch index page → find edition URL
    index_html = _fetch(session, T4127_INDEX_URL)
    edition_url = _find_edition_url(index_html)

    # 2. Fetch edition page (may be a TOC/landing page that links to a sub-page)
    edition_html = _fetch(session, edition_url)
    soup_edition = BeautifulSoup(edition_html, "lxml")

    # 3. Discover the actual formulas document URL.
    #    When t4127-jan.html is a TOC, doc_url will point to the deeper
    #    computer-programs sub-page that contains the real bracket tables.
    doc_url = _find_document_url(edition_url, edition_html)

    # 4. If the formulas live on a sub-page, fetch it now so the parsers
    #    receive the correct HTML.  Cache the edition soup for date extraction.
    if doc_url != edition_url:
        doc_html = _fetch(session, doc_url)
        soup_doc = BeautifulSoup(doc_html, "lxml")
    else:
        doc_html = edition_html
        soup_doc = soup_edition

    # 5. Effective date — try the formulas doc first, then the edition page
    effective_date = _parse_effective_date(soup_doc)
    if effective_date is None:
        effective_date = _parse_effective_date(soup_edition)
    if effective_date is None:
        effective_date = date.today().isoformat()
        logger.warning(
            "Could not parse effective date from T4127; falling back to today (%s)",
            effective_date,
        )

    # 6. Federal data (required — raises if missing).
    #    Try the edition page first: when t4127-jan.html already contains the
    #    bracket tables, parsing it directly is more reliable than following a
    #    TOC link that might land on a topic page without bracket data.
    #    Fall back to soup_doc (the linked sub-page) only when the edition page
    #    itself has no recognizable federal bracket table.
    _data_soup: BeautifulSoup
    _data_html: str
    try:
        federal = _parse_federal(soup_edition, source_url=edition_url)
        _data_soup = soup_edition
        _data_html = edition_html
    except ValueError:
        # Edition page has no bracket data; try the (possibly different) sub-page.
        try:
            federal = _parse_federal(soup_doc, source_url=doc_url)
            _data_soup = soup_doc
            _data_html = doc_html
        except Exception:
            if debug_dir is not None:
                from pathlib import Path as _Path
                debug_path = _Path(debug_dir) / "t4127.html"
                debug_path.parent.mkdir(parents=True, exist_ok=True)
                debug_path.write_text(doc_html, encoding="utf-8")
                logger.info("Debug HTML written to %s", debug_path)
            raise

    # 7. Provincial data (best-effort) — use the same soup that held the
    #    federal bracket data so both come from the same source document.
    provinces = _parse_provinces(_data_soup)
    if not provinces:
        logger.warning(
            "T4127 parser returned no provincial data — "
            "the document structure may have changed"
        )

    # Deduplicated list: index page + edition page + doc page (often the same as edition)
    source_urls = list(dict.fromkeys([T4127_INDEX_URL, edition_url, doc_url]))

    return {
        "bpaf": federal["bpaf"],
        "k1_rate": federal["k1_rate"],
        "tax_brackets": federal["tax_brackets"],
        "effective_date": effective_date,
        "source_urls": source_urls,
        "provinces": provinces,
    }
