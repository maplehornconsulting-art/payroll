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
    "nova scotia": "NS",
    "northwest territories": "NT",
    "nunavut": "NU",
    "ontario": "ON",
    "prince edward island": "PE",
    "saskatchewan": "SK",
    "yukon": "YT",
}

PROVINCES_IN_SCOPE = sorted(PROVINCE_NAME_TO_CODE.values())

# URL path fragments that identify legacy CRA navigation/topic pages.
# Links whose href contains any of these paths must never be used as the
# document URL — they lead to redirect/shell pages with no T4127 content.
_LEGACY_URL_PATHS = (
    "/tax/businesses/topics/",
)

# Regex to extract the month slug from a T4127 edition URL.
# e.g. "…/t4127-jan.html" → group(1) = "jan"
_EDITION_MONTH_RE = re.compile(r"/t4127-([a-z]+)\.html$", re.I)

# Regex to extract the edition number from a T4127 index link's text,
# e.g. "T4127-JAN Payroll Deductions Formulas – 122nd Edition" → 122.
_EDITION_NUMBER_RE = re.compile(r"(\d+)\s*(?:st|nd|rd|th)\s+edition", re.I)

# Regex to detect recognizable federal/chapter content headings in a T4127 page.
_FEDERAL_CONTENT_RE = re.compile(
    r"federal\s+(changes|income\s+tax|tax\s+(rates?|formulas?))"
    r"|chapter\s+\d"
    r"|tax\s+formulas?",
    re.I,
)

# Regexes for parsing BPAF from the canada.ca formula panel (Strategy 0).
# Match an <h4> whose text contains the word "BPAF" (not BPAMB, BPAYT, etc.).
_BPAF_HEADING_PATTERN = re.compile(r"\bBPAF\b", re.I)
# Match "≤ ... BPAF = $X" in the panel text (gives the maximum BPAF).
_LE_DOLLAR_PATTERN = re.compile(
    r"≤.*?BPAF\s*=\s*\$([\d,]+(?:\.\d+)?)", re.I | re.S
)
# Match "≥ ... BPAF = $X" in the panel text (gives the minimum BPAF).
_GE_DOLLAR_PATTERN = re.compile(
    r"≥.*?BPAF\s*=\s*\$([\d,]+(?:\.\d+)?)", re.I | re.S
)


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


def _collect_edition_candidates(index_html: str) -> list[tuple[str, str, str]]:
    """Collect (month, href, link_text) for every JAN/JUL HTML edition link."""
    soup = BeautifulSoup(index_html, "lxml")
    candidates: list[tuple[str, str, str]] = []
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        # Skip PDFs and anything that isn't HTML
        if href.lower().endswith(".pdf"):
            continue
        href_l = href.lower()
        if "t4127" not in href_l:
            continue
        if "jan" in href_l:
            month = "jan"
        elif "jul" in href_l:
            month = "jul"
        else:
            continue
        link_text = " ".join(a.get_text().split())
        candidates.append((month, href, link_text))
    return candidates


def _find_edition_url(index_html: str, today: date | None = None) -> str:
    """Return the URL of the current T4127 HTML edition from the index page.

    Selection logic (in order):

    1. **Edition number** — CRA link text carries an ordinal edition number
       (e.g. "T4127-JAN … – 122nd Edition"). When *every* candidate link has
       one, the highest edition number wins. This is the authoritative signal:
       it correctly picks JAN over a stale prior-year JUL link in H1, and the
       new JUL edition over JAN once CRA publishes it in June.
    2. **Date-aware month preference** (fallback when edition numbers are
       missing from any candidate) — on or after July 1, prefer the JUL
       edition; before July 1, prefer JAN. The previous behaviour of always
       preferring JAN caused ``latest.json`` to keep serving January rates
       for the entire second half of the year.
    3. First candidate in document order, as a last resort.

    Parameters
    ----------
    today:
        Injectable current date for testing; defaults to ``date.today()``.
    """
    if today is None:
        today = date.today()

    candidates = _collect_edition_candidates(index_html)
    if not candidates:
        raise ValueError(
            "Could not find a T4127 HTML edition link on the index page. "
            f"Index URL: {T4127_INDEX_URL}"
        )

    # Strategy 1: highest edition number, but only when every candidate has
    # one — comparing a numbered link against an unnumbered one is meaningless.
    numbered: list[tuple[int, str]] = []
    for _month, href, link_text in candidates:
        m = _EDITION_NUMBER_RE.search(link_text)
        if m:
            numbered.append((int(m.group(1)), href))
    if numbered and len(numbered) == len(candidates):
        numbered.sort(key=lambda t: t[0], reverse=True)
        edition_no, chosen = numbered[0]
        logger.info(
            "T4127 edition selected by edition number %d: %s", edition_no, chosen
        )
        return urljoin(T4127_INDEX_URL, chosen)

    # Strategy 2: date-aware month preference.
    preferred_month = "jul" if today >= date(today.year, 7, 1) else "jan"
    for month, href, _link_text in candidates:
        if month == preferred_month:
            logger.info(
                "T4127 edition selected by month preference (%s, today=%s): %s",
                preferred_month,
                today.isoformat(),
                href,
            )
            return urljoin(T4127_INDEX_URL, href)

    # Strategy 3: first candidate in document order.
    return urljoin(T4127_INDEX_URL, candidates[0][1])


def _find_previous_edition_url(index_html: str, chosen_url: str) -> str | None:
    """Return the URL of the *other* T4127 edition on the index page.

    July editions are delta publications ("refer to the <previous> edition
    for any sections that have not been reproduced"), so the scraper needs
    the referenced prior edition to fill sections the current edition omits
    (federal BPAF, unchanged provinces' claim-code BPAs). Preference: the
    highest-numbered candidate that is not the chosen one; otherwise the
    first non-chosen candidate. Returns ``None`` when the index lists only
    one edition.
    """
    candidates = _collect_edition_candidates(index_html)
    others: list[tuple[int, str]] = []
    unnumbered: list[str] = []
    for _month, href, link_text in candidates:
        resolved = urljoin(T4127_INDEX_URL, href)
        if resolved == chosen_url:
            continue
        m = _EDITION_NUMBER_RE.search(link_text)
        if m:
            others.append((int(m.group(1)), resolved))
        else:
            unnumbered.append(resolved)
    if others:
        others.sort(key=lambda t: t[0], reverse=True)
        return others[0][1]
    if unnumbered:
        return unnumbered[0]
    return None

def _edition_base_url(edition_url: str) -> str:
    """
    Return the sub-directory URL for a T4127 edition page.

    ``"https://…/t4127-jan.html"``  →  ``"https://…/t4127-jan/"``

    This is the directory that contains the chapter sub-pages.
    """
    base_url = edition_url
    if base_url.lower().endswith(".html"):
        base_url = base_url[:-5]  # strip ".html"
    if not base_url.endswith("/"):
        base_url = base_url + "/"
    return base_url


def _synthesise_doc_url(edition_url: str) -> str | None:
    """
    Synthesise the chapter document URL from the edition URL pattern.

    Returns the expected computer-programs sub-page URL, e.g.:

    ``"https://…/t4127-jan/"``
    →  ``"https://…/t4127-jan/t4127-jan-payroll-deductions-formulas-computer-programs.html"``

    Returns ``None`` if the edition URL does not match the expected pattern.
    """
    month_m = _EDITION_MONTH_RE.search(edition_url)
    if not month_m:
        return None
    month = month_m.group(1).lower()
    base = _edition_base_url(edition_url)
    return f"{base}t4127-{month}-payroll-deductions-formulas-computer-programs.html"


def _find_document_url(edition_url: str, edition_html: str) -> str:
    """
    From an edition landing page, find the URL of the actual formulas document.

    If the edition page already contains bracket-like tables or a bulleted-list
    bracket section (2026+ format), it IS the document.

    Otherwise search for a linked sub-page using three layers:

    Layer 1 — Prefer same-directory chapter links; reject legacy
        ``/tax/businesses/topics/`` navigation paths that are dead/redirect
        pages with no T4127 content.  Even when a bad legacy link appears
        first in the page HTML, the same-directory link is preferred.

    Layer 3 — If no suitable link is found at all, synthesise the document
        URL from the known edition URL pattern via :func:`_synthesise_doc_url`.
    """
    soup = BeautifulSoup(edition_html, "lxml")

    # If the page already has a scoring bracket table, it is itself the document
    for table in soup.find_all("table"):
        if _score_bracket_table(table) >= 2:
            return edition_url

    # 2026+ format: edition page may carry bulleted-list brackets instead
    if _parse_brackets_from_ul(soup):
        return edition_url

    # Compute the edition base directory for Layer 1 same-directory preference.
    # e.g. "https://…/t4127-jan.html" → "https://…/t4127-jan/"
    edition_base = _edition_base_url(edition_url)

    # Scan links — collect by preference tier.
    # good_url  : within the edition's own sub-directory (best)
    # other_url : not a legacy path, but not same-dir (acceptable fallback)
    good_url: str | None = None
    other_url: str | None = None

    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_l = href.lower()
        if href_l.endswith(".pdf"):
            continue
        if not (
            "computer-programs" in href_l
            or ("t4127" in href_l and "formulas" in href_l and href_l.endswith(".html"))
        ):
            continue

        # Layer 1: reject legacy CRA navigation/topic-page links
        if any(legacy in href_l for legacy in _LEGACY_URL_PATHS):
            continue

        resolved = urljoin(edition_url, href)
        if resolved.startswith(edition_base):
            if good_url is None:
                good_url = resolved
        elif other_url is None:
            other_url = resolved

    if good_url is not None:
        return good_url
    if other_url is not None:
        return other_url

    # Layer 3: synthesise document URL from the known edition URL pattern.
    synthesised = _synthesise_doc_url(edition_url)
    if synthesised is not None:
        logger.info("Layer 3: synthesised document URL %s", synthesised)
        return synthesised

    # Ultimate fallback: the edition page itself is the document
    return edition_url


def _has_t4127_content(soup: BeautifulSoup) -> bool:
    """
    Return True if *soup* appears to contain real T4127 tax content.

    Used as a Layer-2 sanity check after fetching a candidate document URL.
    If the fetched page is a dead navigation/redirect shell (only
    header/menu/footer chrome with no tax content), this returns False so
    the caller can fall back to an alternative source.
    """
    # Check headings for recognisable federal/chapter content
    for tag in soup.find_all(["h2", "h3"]):
        if _FEDERAL_CONTENT_RE.search(tag.get_text()):
            return True

    # 2026+ bulleted-list bracket format
    if _parse_brackets_from_ul(soup):
        return True

    # Table with a caption mentioning federal income tax
    for table in soup.find_all("table"):
        cap = table.find("caption")
        if cap:
            cap_l = cap.get_text().lower()
            if "federal" in cap_l and ("tax" in cap_l or "income" in cap_l):
                return True
        if _score_bracket_table(table) >= 2:
            return True

    return False


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


def _ul_in_federal_context(ul) -> bool:
    """Return True when *ul* sits under a federal heading (or has no heading).

    Guard for Strategy E: July delta editions carry *provincial* bulleted
    bracket lists (e.g. British Columbia's prorated rates) using the exact
    same "…the tax rate is X%" wording as the federal list. Accepting those
    as federal would publish provincial rates as federal rates. A bracket
    list only counts as federal when the nearest preceding h1–h4 heading
    mentions "federal" (pages with no headings at all are accepted, to keep
    minimal/test pages working).
    """
    heading = ul.find_previous(["h1", "h2", "h3", "h4"])
    if heading is None:
        return True
    return "federal" in heading.get_text(" ", strip=True).lower()


def _parse_brackets_from_ul(soup: BeautifulSoup) -> list[dict]:
    """
    Strategy E: parse federal tax brackets from a bulleted list (2026+ format).

    Primary: find a paragraph whose text contains "tax rates" and
    "as follows", then take the next <ul> or <ol>.

    Secondary (fallback): scan all <ul>/<ol> for lists whose items all match
    the bracket pattern; accept if at least 4 items match.

    Both paths require the list to be in a *federal* context (see
    :func:`_ul_in_federal_context`) so that provincial bracket lists in
    July delta editions are never mistaken for federal brackets.
    """
    # Primary: look for the lead-in sentence, then take the next <ul>/<ol>.
    # Use find_all_next with a limit to avoid scanning the full document.
    for p in soup.find_all(["p", "li", "div"]):
        text = " ".join(p.get_text().split()).lower()
        if "tax rates" in text and "as follows" in text:
            for sib in p.find_all_next(limit=15):
                if sib.name in ("ul", "ol"):
                    if not _ul_in_federal_context(sib):
                        break
                    brackets = _parse_ul_bracket_items(sib)
                    if brackets:
                        return brackets
                    break
                if sib.name in ("h1", "h2", "h3"):
                    break

    # Secondary: scan all <ul>/<ol> for at least 4 bracket-like items
    for ul in soup.find_all(["ul", "ol"]):
        if not _ul_in_federal_context(ul):
            continue
        brackets = _parse_ul_bracket_items(ul)
        if len(brackets) >= 4:
            return brackets

    return []



# ---------------------------------------------------------------------------
# Federal section
# ---------------------------------------------------------------------------

# Plausible range for the Canada Employment Amount (CEA) indexed value.
# Historical values: 2025=$1,471, 2026=$1,500.  The range is wide to survive
# several years of indexing without requiring a code change.
_CEA_MIN_PLAUSIBLE = 1_000.0
_CEA_MAX_PLAUSIBLE = 5_000.0


def _parse_cea(soup: BeautifulSoup) -> float | None:
    """Try to extract the Canada Employment Amount (CEA) from the T4127 HTML.

    CRA T4127 defines CEA in the "Definitions of variables" section (Chapter 5).
    It appears near phrases like "Canada employment amount" or the token "CEA".

    Returns the parsed dollar value when found, or *None* when the page
    structure does not yield a confident result (the caller should then fall
    back to the hard-coded parameter value already in the Odoo database and
    log a warning so the value is reviewed at annual update time).

    .. note::
        This extraction is best-effort.  CRA sometimes embeds CEA in a prose
        paragraph rather than a structured table, making reliable parsing
        fragile.  If the scraper returns *None*, the existing hard-coded rule
        parameter value ($1,500 for 2026) remains in effect — no data is lost.
        **Annual review:** confirm the CEA value each January when CRA releases
        the updated T4127 and update ``rule_parameter_l10n_ca_fed_canada_employment_amount``
        if needed.
    """
    text = soup.get_text(" ", strip=True)

    # Pattern 1: "canada employment amount ... $X,XXX" within ~200 chars
    cea_re = re.compile(
        r"canada\s+employment\s+amount[^$\d]{0,200}\$([\d,]+(?:\.\d+)?)",
        re.I,
    )
    m = cea_re.search(text)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            if _CEA_MIN_PLAUSIBLE <= v <= _CEA_MAX_PLAUSIBLE:
                return v
        except ValueError:
            pass

    # Pattern 2: "CEA = $X,XXX" or "CEA is $X,XXX"
    cea_eq_re = re.compile(
        r"\bCEA\s*(?:=|is)\s*\$([\d,]+(?:\.\d+)?)",
        re.I,
    )
    m = cea_eq_re.search(text)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            if _CEA_MIN_PLAUSIBLE <= v <= _CEA_MAX_PLAUSIBLE:
                return v
        except ValueError:
            pass

    # Pattern 3: "$X,XXX ... canada employment amount" (reverse order)
    cea_rev_re = re.compile(
        r"\$([\d,]+(?:\.\d+)?)[^$\d]{0,200}canada\s+employment\s+amount",
        re.I,
    )
    m = cea_rev_re.search(text)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            if _CEA_MIN_PLAUSIBLE <= v <= _CEA_MAX_PLAUSIBLE:
                return v
        except ValueError:
            pass

    return None


def _parse_federal(
    soup: BeautifulSoup, source_url: str = "", require_bpaf: bool = True
) -> dict:
    """
    Extract federal income tax brackets, BPAF min/max, K1 rate, and CEA.

    Uses multiple strategies so minor changes to canada.ca HTML layout do
    not cause hard failures:

    * Strategy F – Table 8.1 Federal block (most authoritative when present).
    * Strategy E – bulleted-list extraction (2026+ format, federal-context
      guarded so provincial lists in July delta editions are never matched).
    * Strategy A – find a known heading phrase, take the first table after it.
    * Strategy D – table caption match.
    * Strategy B – score all tables by how bracket-table-like they look; accept
      the highest-scoring one (minimum score 3).
    * Strategy C – anchor on a known dollar/rate token and walk up to a table.

    Parameters
    ----------
    require_bpaf:
        When True (default), a BPAF parse failure raises ``ValueError``.
        When False, BPAF failure returns ``"bpaf": None`` — used for July
        delta editions, which omit the federal BPAF section ("refer to the
        previous edition for any sections that have not been reproduced");
        the caller then fills BPAF from the referenced prior edition.

    Returns::

        {
            "tax_brackets": [...],
            "bpaf": {"min": float, "max": float} | None,
            "k1_rate": float,
            "cea": float | None,   # None when automatic extraction fails
        }
    """
    def _bpaf_or_none(k1_rate: float) -> dict | None:
        try:
            return _parse_bpaf(soup, k1_rate)
        except ValueError:
            if require_bpaf:
                raise
            logger.warning(
                "Federal BPAF not present in this T4127 document (expected for "
                "July delta editions); will fill from the referenced prior edition."
            )
            return None

    # Strategy F — Table 8.1 Federal block (2026+ format)
    brackets_81 = _parse_table_81_all(soup).get("Federal")
    if brackets_81:
        logger.info("Federal brackets located via Strategy F (Table 8.1)")
        k1_rate = brackets_81[0]["rate"]
        bpaf = _bpaf_or_none(k1_rate)
        cea = _parse_cea(soup)
        if cea is None:
            logger.warning(
                "Could not automatically extract Canada Employment Amount (CEA) from "
                "T4127 HTML. The existing rule parameter value will be used unchanged. "
                "Review rule_parameter_l10n_ca_fed_canada_employment_amount annually."
            )
        return {"tax_brackets": brackets_81, "bpaf": bpaf, "k1_rate": k1_rate, "cea": cea}

    # Strategy E — bulleted list (2026+ format)
    brackets_ul = _parse_brackets_from_ul(soup)
    if brackets_ul:
        logger.info("Federal brackets located via Strategy E (bulleted list)")
        k1_rate = brackets_ul[0]["rate"]
        bpaf = _bpaf_or_none(k1_rate)
        cea = _parse_cea(soup)
        if cea is None:
            logger.warning(
                "Could not automatically extract Canada Employment Amount (CEA) from "
                "T4127 HTML. The existing rule parameter value will be used unchanged. "
                "Review rule_parameter_l10n_ca_fed_canada_employment_amount annually."
            )
        return {"tax_brackets": brackets_ul, "bpaf": bpaf, "k1_rate": k1_rate, "cea": cea}

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
    bpaf = _bpaf_or_none(k1_rate)

    cea = _parse_cea(soup)
    if cea is None:
        logger.warning(
            "Could not automatically extract Canada Employment Amount (CEA) from "
            "T4127 HTML. The existing rule parameter value will be used unchanged. "
            "Review rule_parameter_l10n_ca_fed_canada_employment_amount annually."
        )

    return {"tax_brackets": brackets, "bpaf": bpaf, "k1_rate": k1_rate, "cea": cea}


def _parse_bpaf_from_formula_panel(soup: BeautifulSoup) -> dict | None:
    """Strategy 0: parse BPAF max/min from the canada.ca formula panel.

    Looks for an <h4> heading whose text contains "BPAF" (word boundary, so
    BPAMB/BPAYT are excluded), then scans the immediately following
    <div class="panel"> sibling for paragraphs containing:
      - "≤ ... BPAF = $X"  → maximum BPAF
      - "≥ ... BPAF = $X"  → minimum BPAF

    Returns {"max": float, "min": float} on success, None on failure.
    """
    for h4 in soup.find_all("h4"):
        if not _BPAF_HEADING_PATTERN.search(h4.get_text(" ", strip=True)):
            continue
        # Search the next 10 siblings/descendants for the panel <div>.
        # 10 is generous for the expected page structure: the panel is typically
        # the immediate next sibling (a whitespace text node then the div).
        panel = None
        for sib in h4.find_all_next(limit=10):
            if sib.name == "div" and "panel" in (sib.get("class") or []):
                panel = sib
                break
            # Stop scanning when we reach the next heading (different formula)
            if sib.name == "h4" and sib is not h4:
                break
        if panel is None:
            continue
        text = panel.get_text(" ", strip=True)
        max_match = _LE_DOLLAR_PATTERN.search(text)
        min_match = _GE_DOLLAR_PATTERN.search(text)
        if max_match and min_match:
            return {
                "max": _parse_num(max_match.group(1)),
                "min": _parse_num(min_match.group(1)),
            }
    return None


def _parse_bpaf(soup: BeautifulSoup, k1_rate: float) -> dict:
    """
    Extract BPAF maximum and minimum from the T4127 HTML.

    Tries three strategies in order:

    * Strategy 0: <h4> heading containing "BPAF" followed by a <div class="panel">
      with paragraphs using ≤ / ≥ symbols (2026+ canada.ca formula-panel format).
    * Strategy 1: dedicated BPAF / BPA table (caption match).
    * Strategy 2: dollar amounts adjacent to "maximum" / "minimum" keywords.

    Raises ValueError if no strategy succeeds rather than silently falling back
    to a page-wide dollar-amount scan, which can return plausible-looking but
    completely wrong values.
    """
    BPA_MIN_PLAUSIBLE = 5_000.0
    BPA_MAX_PLAUSIBLE = 30_000.0

    def _is_bpa(v: float) -> bool:
        return BPA_MIN_PLAUSIBLE <= v <= BPA_MAX_PLAUSIBLE

    def _sanity_check(result: dict) -> dict:
        """Validate BPAF result before returning it."""
        bpaf_max = result["max"]
        bpaf_min = result["min"]
        if not (bpaf_max > bpaf_min > 0):
            raise ValueError(
                f"BPAF sanity check failed: max={bpaf_max}, min={bpaf_min}. "
                f"Expected max > min > 0."
            )
        # Plausibility bounds based on historical CRA BPAF values (2024–2030):
        # min has ranged ~$14k–$15.5k; max has ranged ~$15k–$17k.
        _BPAF_MIN_LOWER = 10_000.0   # absolute floor — much lower means wrong data
        _BPAF_MIN_UPPER = 20_000.0   # upper bound for the minimum BPAF
        _BPAF_MAX_LOWER = 12_000.0   # lower bound for the maximum BPAF
        _BPAF_MAX_UPPER = 25_000.0   # absolute ceiling — much higher means wrong data
        if not (
            _BPAF_MIN_LOWER <= bpaf_min <= _BPAF_MIN_UPPER
            and _BPAF_MAX_LOWER <= bpaf_max <= _BPAF_MAX_UPPER
        ):
            raise ValueError(
                f"BPAF plausibility check failed: max={bpaf_max}, min={bpaf_min}. "
                f"Expected min in [{_BPAF_MIN_LOWER/1000:.0f}k,{_BPAF_MIN_UPPER/1000:.0f}k]"
                f" and max in [{_BPAF_MAX_LOWER/1000:.0f}k,{_BPAF_MAX_UPPER/1000:.0f}k]"
                f" for 2024-2030."
            )
        return result

    # Strategy 0: 2026+ formula-panel format (<h4> + <div class="panel">)
    result = _parse_bpaf_from_formula_panel(soup)
    if result is not None:
        logger.info("BPAF located via Strategy 0 (formula panel)")
        return _sanity_check(result)

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
                    return _sanity_check({"max": max(amounts), "min": min(amounts)})

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
        return _sanity_check({"max": max_bpa, "min": min_bpa})
    if max_bpa is not None:
        # Only maximum found: minimum defaults to maximum (no phase-out)
        return _sanity_check({"max": max_bpa, "min": max_bpa})

    raise ValueError(
        "Could not locate federal BPAF on T4127 page. "
        "CRA may have changed the page format. Check dist/_debug/t4127.html "
        "and update _parse_bpaf in cra_feed/parsers/t4127.py."
    )


# ---------------------------------------------------------------------------
# Provincial sections
# ---------------------------------------------------------------------------

def _parse_table_81_all(soup: BeautifulSoup) -> dict[str, list[dict]]:
    """
    Parse Table 8.1 from the 2026+ T4127 format, INCLUDING the Federal block.

    Table 8.1 consolidates federal and all provincial/territorial rates
    (R, V), income thresholds (A), and constants (K, KP) into a single grid.

    Layout::

        row: ['Federal', 'A', '0', '58,523', ...]   # Federal thresholds
        row: ['R', '0.1400', '0.2050', ...]          # Federal rates
        row: ['K', '0', '3,804', ...]                # Federal constants – skip
        row: ['AB', 'A', '0', '61,200', '154,259', ...] # AB thresholds
        row: ['V', '0.0800', '0.1000', ...]          # AB rates
        row: ['KP', '0', '1,224', ...]               # AB constants – skip
        ...

    Returns
    -------
    dict[str, list[dict]]
        ``{code: [{"up_to": float | None, "rate": float}, ...]}`` where
        *code* is a 2-letter province code or the literal ``"Federal"``.
        Only entries with at least 2 brackets are included.
        Returns an empty dict if Table 8.1 is not found in the HTML.
    """
    known_codes = set(PROVINCE_NAME_TO_CODE.values())

    # Locate Table 8.1
    table_81 = None
    for table in soup.find_all("table"):
        cap = table.find("caption")
        if cap and "Table 8.1" in cap.get_text(" ", strip=True):
            cap_text = cap.get_text(" ", strip=True)
            # "Table 8.11", "Table 8.14" (claim codes) also contain the
            # substring "Table 8.1" — require the char after "8.1" to be a
            # non-digit so claim-codes tables are never selected here.
            m = re.search(r"Table\s+8\.1(?!\d)", cap_text)
            if m:
                table_81 = table
                break

    if table_81 is None:
        return {}

    thresholds_by_code: dict[str, list[float]] = {}
    rates_by_code: dict[str, list[float]] = {}
    current_code: str | None = None

    for row in table_81.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        cell_texts = [c.get_text(" ", strip=True) for c in cells]
        first = cell_texts[0].strip()
        second = cell_texts[1].strip() if len(cell_texts) >= 2 else ""

        # Threshold row: second cell is "A"
        if second == "A":
            if first == "Federal" or first in known_codes:
                current_code = first
                thresholds: list[float] = []
                for t in cell_texts[2:]:
                    t_s = t.strip()
                    if not t_s:
                        continue
                    try:
                        thresholds.append(float(t_s.replace(",", "").replace("$", "")))
                    except ValueError:
                        continue
                thresholds_by_code[current_code] = thresholds
            else:
                current_code = None
            continue

        # Constants rows – not needed
        if first in ("K", "KP"):
            continue

        # Rate row: "V" for provinces, "R" for Federal
        if first in ("V", "R"):
            expected = "R" if current_code == "Federal" else "V"
            if first == expected and current_code is not None:
                rates: list[float] = []
                for t in cell_texts[1:]:
                    t_s = t.strip()
                    if not t_s:
                        continue
                    try:
                        rates.append(float(t_s.replace(",", "").replace("%", "")))
                    except ValueError:
                        continue
                rates_by_code[current_code] = rates
            continue

    # Build bracket lists from accumulated thresholds and rates
    result: dict[str, list[dict]] = {}
    for code in thresholds_by_code:
        if code not in rates_by_code:
            continue
        thresholds = thresholds_by_code[code]
        rates = rates_by_code[code]
        n = len(rates)
        if n < 1:
            continue

        brackets: list[dict] = []
        for i, rate in enumerate(rates):
            if rate > 1:  # percentage notation (e.g. 8.0 → 0.08)
                rate = rate / 100.0
            up_to: float | None = thresholds[i + 1] if i + 1 < len(thresholds) else None
            brackets.append({"up_to": up_to, "rate": rate})

        if len(brackets) >= 2:
            result[code] = brackets

    return result


def _parse_table_81(soup: BeautifulSoup) -> dict[str, list[dict]]:
    """Provinces-only view of Table 8.1 (see :func:`_parse_table_81_all`)."""
    result = _parse_table_81_all(soup)
    result.pop("Federal", None)
    return result



def _parse_claim_code_bpas(soup: BeautifulSoup) -> dict[str, dict]:
    """
    Parse BPA (and optional K1P) for all provinces from claim codes tables.

    Iterates tables whose captions match ``"Table 8.NN <province> claim codes"``
    (2026+ format) and extracts claim code 1's "Total claim amount ($) to" value
    as the BPA and, when present, "Option 1, K1P ($)" as K1P.

    Returns
    -------
    dict[str, dict]
        ``{prov_code: {"bpa": float}}`` or
        ``{prov_code: {"bpa": float, "k1p": float}}`` per province.
    """
    prov_lower_to_code = {k.lower(): v for k, v in PROVINCE_NAME_TO_CODE.items()}
    caption_re = re.compile(r"Table\s+8\.\d+\s+(.+?)\s+claim\s+codes", re.I)

    result: dict[str, dict] = {}

    for table in soup.find_all("table"):
        cap = table.find("caption")
        if not cap:
            continue
        cap_text = cap.get_text(" ", strip=True)
        m = caption_re.search(cap_text)
        if not m:
            continue

        prov_name_raw = m.group(1).strip()
        # Strip trailing parenthetical, e.g. "(Using maximum BPAMB)"
        prov_name_clean = re.sub(r"\s*\(.*?\)\s*$", "", prov_name_raw, flags=re.I).strip()

        if prov_name_clean.lower() in ("federal", ""):
            continue

        code = prov_lower_to_code.get(prov_name_clean.lower())
        if code is None:
            logger.debug(
                "Claim codes table with unknown province name: %r", prov_name_raw
            )
            continue

        # Locate headers and find claim code 1 row (reuse Strategy 5 logic)
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(" ", strip=True).lower() for c in header_cells]

        claim_code_col = next(
            (i for i, h in enumerate(headers) if "claim code" in h), None
        )
        total_to_col = next(
            (
                i
                for i, h in enumerate(headers)
                if "total claim amount" in h and "to" in h.split()
            ),
            None,
        )
        k1p_col = next((i for i, h in enumerate(headers) if "k1p" in h), None)

        if claim_code_col is None or total_to_col is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if claim_code_col >= len(cells):
                continue
            if cells[claim_code_col].get_text(strip=True) != "1":
                continue
            if total_to_col >= len(cells):
                continue
            bpa_text = cells[total_to_col].get_text(strip=True).replace(",", "")
            try:
                bpa_val = float(bpa_text)
            except ValueError:
                continue
            if not (5_000 < bpa_val < 50_000):
                continue
            bpa_info: dict = {"bpa": bpa_val}
            if k1p_col is not None and k1p_col < len(cells):
                k1p_text = cells[k1p_col].get_text(strip=True).replace(",", "")
                try:
                    k1p_val = float(k1p_text)
                    if k1p_val >= 0:
                        bpa_info["k1p"] = k1p_val
                except ValueError:
                    pass
            result[code] = bpa_info
            break

    return result


def _parse_table_82_surtaxes(soup: BeautifulSoup) -> dict[str, list[list[float]]]:
    """
    Parse Table 8.2 (Other rates and amounts) for provincial surtax bands.

    Surtax bands appear only as short continuation rows immediately after a
    province row. A continuation row has exactly 2 non-empty cells where the
    first is a dollar threshold (> 100) and the second is a decimal rate in
    (0, 1]. Province rows themselves are NEVER treated as surtax data — even
    though their Basic amount + Index rate cells superficially match the
    [threshold, rate] shape.

    Returns
    -------
    dict[str, list[list[float]]]
        ``{prov_code: [[threshold, rate], ...]}`` — only provinces with at
        least one continuation row are included. Empty dict otherwise.
    """
    known_codes = set(PROVINCE_NAME_TO_CODE.values())

    # Locate Table 8.2 by caption.
    table_82 = None
    for table in soup.find_all("table"):
        cap = table.find("caption")
        if cap and "Table 8.2" in cap.get_text(" ", strip=True):
            table_82 = table
            break
    if table_82 is None:
        return {}

    result: dict[str, list[list[float]]] = {}
    current_prov: str | None = None

    for row in table_82.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        cell_texts = [c.get_text(" ", strip=True) for c in cells]
        first = cell_texts[0].strip()

        # Province row: starts a new context. NEVER emit surtax from this row
        # because its 2nd/3rd cells are BPA / Index rate, not surtax bands.
        if first in known_codes:
            current_prov = first
            continue

        # Federal / QC / "Outside Canada" / unknown header row → reset context
        if first in ("Federal", "QC", "Outside Canada", ""):
            # An empty first cell is permitted ONLY if the row is a 2-cell
            # continuation row (handled below). Otherwise reset.
            # Note: a header row with first=="" and many non-empty cells will
            # also be reset here, which is the correct behaviour.
            non_empty = [t for t in cell_texts if t.strip()]
            if first != "" or len(non_empty) != 2:
                current_prov = None
                continue
            # Fall through: empty-first-cell row with exactly 2 non-empty cells
            # is treated as a continuation row by the logic below.

        if current_prov is None:
            continue

        # Continuation row candidate: collect non-empty cells and try to
        # parse exactly two values: a dollar threshold + a decimal rate.
        non_empty = [t for t in cell_texts if t.strip()]
        if len(non_empty) != 2:
            # Not a surtax continuation row.
            # If the first cell looks like a province code we already handled
            # it above; anything else with ≠2 non-empty cells means we are
            # done with the previous province's surtax block.
            current_prov = None
            continue

        try:
            v1 = float(non_empty[0].replace(",", "").replace("$", ""))
            v2_raw = non_empty[1].strip()
            v2_is_pct = v2_raw.endswith("%")
            v2 = float(v2_raw.replace(",", "").replace("$", "").rstrip("%"))
            if v2_is_pct:
                v2 /= 100.0
        except ValueError:
            current_prov = None
            continue

        # Validate shapes: threshold must be > 100, rate must be in (0, 1].
        if v1 > 100 and 0 < v2 <= 1:
            result.setdefault(current_prov, []).append([v1, v2])
        else:
            current_prov = None

    return result


def _parse_provinces(
    soup: BeautifulSoup, require_bpa: bool = True
) -> dict[str, dict]:
    """
    Parse all in-scope provincial/territorial tax data from the T4127 HTML.

    Returns a dict keyed by 2-letter province code with values::

        {"bpa": float | None, "tax_brackets": [...], "surtax": [...]}

    Parameters
    ----------
    require_bpa:
        When True (default), a province with tax brackets but no parsable BPA
        aborts the scrape (``ValueError``) — defaulting to $0 would
        over-withhold employee tax. When False, such provinces are returned
        with ``"bpa": None`` — used for July delta editions, which reproduce
        claim-code tables only for changed provinces; the caller fills the
        missing BPAs from the referenced prior edition and enforces
        completeness after the merge.
    """
    provinces: dict[str, dict] = {}

    # 2026+ format: Table 8.1 consolidates all provincial brackets.
    brackets_by_code = _parse_table_81(soup)
    if brackets_by_code:
        bpas_by_code = _parse_claim_code_bpas(soup)
        for code, brackets in brackets_by_code.items():
            if code not in bpas_by_code:
                if require_bpa:
                    raise ValueError(
                        f"Province {code!r} has tax brackets from Table 8.1 but no BPA "
                        f"found in claim codes tables. A missing BPA must abort the scrape "
                        f"because defaulting to $0 would over-withhold employee tax."
                    )
                logger.info(
                    "Province %s: brackets present but no claim-codes BPA in this "
                    "document (expected for July delta editions); will fill from "
                    "the referenced prior edition.",
                    code,
                )
                provinces[code] = {"bpa": None, "tax_brackets": brackets}
                continue
            bpa_info = bpas_by_code[code]
            prov_result: dict = {"bpa": bpa_info["bpa"], "tax_brackets": brackets}
            if bpa_info.get("k1p") is not None:
                prov_result["k1p"] = bpa_info["k1p"]
            provinces[code] = prov_result

        surtaxes = _parse_table_82_surtaxes(soup)
        for code in PROVINCE_NAME_TO_CODE.values():
            if code in provinces:
                provinces[code]["surtax"] = surtaxes.get(code, [])
        return provinces

    # Fallback: legacy per-province <h3>/<h4> section format (pre-2026).
    for prov_name, code in PROVINCE_NAME_TO_CODE.items():
        try:
            prov_data = _parse_one_province(soup, prov_name, code)
            if prov_data:
                provinces[code] = prov_data
        except ValueError:
            # BPA parse failure (or other data error) → abort scrape.
            # Re-raise so the caller receives a hard error rather than a
            # silently-zeroed BPA in the output feed.
            raise
        except Exception as exc:
            logger.warning("Could not parse province %s (%s): %s", code, prov_name, exc)

    surtaxes = _parse_table_82_surtaxes(soup)
    for code in PROVINCE_NAME_TO_CODE.values():
        if code in provinces:
            provinces[code]["surtax"] = surtaxes.get(code, [])

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
    # 2026+ format: provincial brackets in bulleted-list form (try first)
    brackets: list[dict] = _parse_brackets_from_ul(section_soup)

    # Legacy table-based format
    if not brackets:
        table, _strategy, _heading = _find_table_after_heading_or_fingerprint(
            section_soup,
            prov_heading_candidates,
            _score_bracket_table,
        )
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

    # --- BPA (and optional K1P) ---
    bpa_result = _parse_province_bpa(section_soup, prov_name)
    result: dict = {"bpa": bpa_result["bpa"], "tax_brackets": brackets}
    if "k1p" in bpa_result:
        result["k1p"] = bpa_result["k1p"]
    return result


def _parse_province_bpa(section_soup, prov_name: str) -> dict:
    """
    Extract the provincial Basic Personal Amount (and optional K1P) from a
    province's HTML section.

    Tries four strategies in order:
    1. Dollar amount explicitly labeled as "basic personal amount" or "BPA".
    2. Same keywords, dollar amount preceding the label.
    3. List items / paragraphs containing BPA keywords.
    4. Largest plausible dollar amount in the section.
    5. Claim codes table — for provinces (e.g. BC, NL, NT, NU) where CRA
       embeds the BPA in a "claim codes" table rather than a standalone line.
       Claim code 1's "Total claim amount ($) to" cell = BPA; the matching
       "Option 1, K1P ($)" cell (if present) is also returned.

    Returns
    -------
    dict
        Always contains ``"bpa": float``.  Contains ``"k1p": float`` when the
        value was extracted from a claim codes table.

    Raises
    ------
    ValueError
        When no plausible BPA dollar amount can be found.  This is a hard
        error — silently defaulting to $0 would over-withhold employee tax.
    """
    text = section_soup.get_text(" ")

    # Strategy 1: amounts explicitly labeled as BPA / basic personal amount
    # Handles: "basic personal amount: $12,000" or "BPA – $12,000"
    bpa_re = re.compile(
        r"(?:basic\s+personal(?:\s+\w+){0,2}|bpa)[^$\d]{0,60}\$([\d,]+(?:\.\d+)?)",
        re.I,
    )
    m = bpa_re.search(text)
    if m:
        try:
            return {"bpa": float(m.group(1).replace(",", ""))}
        except ValueError:
            pass

    # Strategy 2: "$X,XXX" near "basic personal" in reverse order
    bpa_rev_re = re.compile(
        r"\$([\d,]+(?:\.\d+)?)[^$\d]{0,60}(?:basic\s+personal(?:\s+\w+){0,2}|bpa)",
        re.I,
    )
    m = bpa_rev_re.search(text)
    if m:
        try:
            return {"bpa": float(m.group(1).replace(",", ""))}
        except ValueError:
            pass

    # Strategy 3: search list items and paragraphs for BPA keywords + amount
    for tag in section_soup.find_all(["li", "p"]):
        tag_text = tag.get_text(" ", strip=True)
        tag_lower = tag_text.lower()
        if "basic personal" not in tag_lower and "bpa" not in tag_lower:
            continue
        for amt_m in re.finditer(r"\$([\d,]+(?:\.\d+)?)", tag_text):
            try:
                v = float(amt_m.group(1).replace(",", ""))
                if 5_000 < v < 50_000:
                    return {"bpa": v}
            except ValueError:
                pass

    # Strategy 4: largest plausible dollar amount in the section
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
        return {"bpa": max(plausible)}

    # Strategy 5: claim codes table (last resort — used by BC, NL, NT, NU).
    # CRA publishes BPA as claim code 1's "Total claim amount ($) to" value
    # rather than a standalone line for these provinces/territories.
    for table in section_soup.find_all("table"):
        cap = table.find("caption")
        context = (cap.get_text(" ", strip=True) if cap else "").lower()
        if "claim codes" not in context:
            continue

        # Locate header row and identify relevant columns.
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(" ", strip=True).lower() for c in header_cells]

        claim_code_col = next(
            (i for i, h in enumerate(headers) if "claim code" in h), None
        )
        total_to_col = next(
            (
                i for i, h in enumerate(headers)
                if "total claim amount" in h and "to" in h.split()
            ),
            None,
        )
        k1p_col = next(
            (i for i, h in enumerate(headers) if "k1p" in h), None
        )

        if claim_code_col is None or total_to_col is None:
            continue

        # Find claim code 1 row.
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if claim_code_col >= len(cells):
                continue
            if cells[claim_code_col].get_text(strip=True) != "1":
                continue
            if total_to_col >= len(cells):
                continue
            bpa_text = cells[total_to_col].get_text(strip=True).replace(",", "")
            try:
                bpa_val = float(bpa_text)
            except ValueError:
                continue
            if not (5_000 < bpa_val < 50_000):
                continue
            result: dict = {"bpa": bpa_val}
            if k1p_col is not None and k1p_col < len(cells):
                k1p_text = cells[k1p_col].get_text(strip=True).replace(",", "")
                try:
                    k1p_val = float(k1p_text)
                    if k1p_val >= 0:
                        result["k1p"] = k1p_val
                except ValueError:
                    pass
            return result

    raise ValueError(
        f"Could not parse BPA for province {prov_name!r}. "
        f"No plausible BPA dollar amount (between $5,000 and $50,000) found. "
        f"Section text excerpt: {text[:300]!r}"
    )


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

    # 4b. Layer 2: validate the fetched document page actually has T4127 content.
    #     If the chosen doc_url turned out to be a dead navigation/redirect shell,
    #     try the synthesised URL as a safety net before the parsing step.
    if doc_url != edition_url and not _has_t4127_content(soup_doc):
        logger.warning(
            "Document URL %s appears to be a navigation shell (no T4127 content). "
            "Attempting synthesised fallback URL.",
            doc_url,
        )
        fallback_doc_url = _synthesise_doc_url(edition_url)
        if fallback_doc_url is not None and fallback_doc_url != doc_url:
            fallback_html = _fetch(session, fallback_doc_url)
            fallback_soup = BeautifulSoup(fallback_html, "lxml")
            if _has_t4127_content(fallback_soup):
                logger.info(
                    "Layer 2 fallback: using synthesised URL %s", fallback_doc_url
                )
                doc_url = fallback_doc_url
                doc_html = fallback_html
                soup_doc = fallback_soup

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
    #    BPAF is allowed to be missing at this stage: July editions are delta
    #    publications ("refer to the previous edition for any sections that
    #    have not been reproduced") and omit the federal BPAF section when it
    #    is unchanged. Missing pieces are filled from the referenced prior
    #    edition below, and completeness is enforced after the merge.
    _data_soup: BeautifulSoup
    _data_html: str
    try:
        federal = _parse_federal(soup_edition, source_url=edition_url, require_bpaf=False)
        _data_soup = soup_edition
        _data_html = edition_html
    except ValueError:
        # Edition page has no bracket data; try the (possibly different) sub-page.
        try:
            federal = _parse_federal(soup_doc, source_url=doc_url, require_bpaf=False)
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

    # 7. Provincial data — use the same soup that held the federal bracket
    #    data so both come from the same source document. BPAs are allowed to
    #    be missing at this stage (July delta editions reproduce claim-code
    #    tables only for changed provinces); enforced after the merge.
    provinces = _parse_provinces(_data_soup, require_bpa=False)
    if not provinces:
        logger.warning(
            "T4127 parser returned no provincial data — "
            "the document structure may have changed"
        )

    # 8. Delta-edition merge: when the chosen document omitted the federal
    #    BPAF or any province's BPA, fetch the referenced prior edition from
    #    the index page and fill the gaps. Current-edition values always win;
    #    the prior edition only supplies what the current one omitted.
    prev_source_urls: list[str] = []
    missing_bpaf = federal.get("bpaf") is None
    missing_bpa_codes = sorted(
        code for code, pdata in provinces.items() if pdata.get("bpa") is None
    )
    if missing_bpaf or missing_bpa_codes:
        logger.info(
            "Delta edition detected (missing federal BPAF: %s; provinces missing "
            "BPA: %s). Fetching the referenced prior edition to fill gaps.",
            missing_bpaf,
            ", ".join(missing_bpa_codes) or "none",
        )
        prev_edition_url = _find_previous_edition_url(index_html, edition_url)
        if prev_edition_url is None:
            raise ValueError(
                "Current T4127 edition is a delta publication (federal BPAF "
                "and/or provincial BPAs not reproduced) but no prior edition "
                "link was found on the index page to fill the gaps. "
                f"Index URL: {T4127_INDEX_URL}"
            )

        prev_edition_html = _fetch(session, prev_edition_url)
        prev_doc_url = _find_document_url(prev_edition_url, prev_edition_html)
        if prev_doc_url != prev_edition_url:
            prev_doc_html = _fetch(session, prev_doc_url)
        else:
            prev_doc_html = prev_edition_html
        prev_soup = BeautifulSoup(prev_doc_html, "lxml")
        prev_source_urls = [prev_edition_url, prev_doc_url]

        # Fill federal BPAF from the prior edition.
        if missing_bpaf:
            federal["bpaf"] = _parse_bpaf(prev_soup, federal["k1_rate"])
            logger.info(
                "Filled federal BPAF from prior edition %s: %s",
                prev_doc_url,
                federal["bpaf"],
            )

        # Fill missing provincial BPAs (and K1P) from the prior edition's
        # claim-code tables; fall back to a full province parse for legacy
        # per-section formats.
        if missing_bpa_codes:
            prev_bpas = _parse_claim_code_bpas(prev_soup)
            if not prev_bpas:
                prev_provinces = _parse_provinces(prev_soup, require_bpa=False)
                prev_bpas = {
                    code: {
                        k: v
                        for k, v in (("bpa", pdata.get("bpa")), ("k1p", pdata.get("k1p")))
                        if v is not None
                    }
                    for code, pdata in prev_provinces.items()
                    if pdata.get("bpa") is not None
                }
            for code in missing_bpa_codes:
                prev_info = prev_bpas.get(code)
                if prev_info is None or prev_info.get("bpa") is None:
                    continue
                provinces[code]["bpa"] = prev_info["bpa"]
                if provinces[code].get("k1p") is None and prev_info.get("k1p") is not None:
                    provinces[code]["k1p"] = prev_info["k1p"]
            filled = [
                code for code in missing_bpa_codes if provinces[code].get("bpa") is not None
            ]
            logger.info(
                "Filled BPAs from prior edition %s for: %s",
                prev_doc_url,
                ", ".join(filled) or "none",
            )

    # 9. Enforce completeness after the merge — the original safety rule:
    #    a missing BPAF or BPA must abort the scrape because defaulting to $0
    #    would over-withhold employee tax.
    if federal.get("bpaf") is None:
        raise ValueError(
            "Could not locate federal BPAF in the current T4127 edition or the "
            "referenced prior edition. CRA may have changed the page format."
        )
    still_missing = sorted(
        code for code, pdata in provinces.items() if pdata.get("bpa") is None
    )
    if still_missing:
        raise ValueError(
            f"Provinces {', '.join(still_missing)} have tax brackets but no BPA in "
            f"the current T4127 edition or the referenced prior edition. A missing "
            f"BPA must abort the scrape because defaulting to $0 would "
            f"over-withhold employee tax."
        )

    # Deduplicated list: index page + edition page + doc page (often the same
    # as edition) + any prior-edition pages used for the delta merge.
    source_urls = list(
        dict.fromkeys([T4127_INDEX_URL, edition_url, doc_url, *prev_source_urls])
    )

    return {
        "bpaf": federal["bpaf"],
        "k1_rate": federal["k1_rate"],
        "tax_brackets": federal["tax_brackets"],
        "cea": federal.get("cea"),
        "effective_date": effective_date,
        "source_urls": source_urls,
        "provinces": provinces,
    }
