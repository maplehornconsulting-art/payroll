"""Real parser for the CRA T4127 Payroll Deductions Formulas publication.

Fetches the T4127 index page, discovers the current HTML edition URL, and
parses federal income tax brackets, BPAF, K1 rate, effective date, and
all provincial/territorial tax data (excluding Quebec).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from urllib.parse import urljoin

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

    If the edition page already contains tax data (headings or tables with
    income/bracket text), it IS the document.  Otherwise follow the first
    'computer-programs' or 'formulas' link.
    """
    text_l = edition_html.lower()
    if any(kw in text_l for kw in ("taxable income", "net income", "tax bracket")):
        return edition_url

    soup = BeautifulSoup(edition_html, "lxml")
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


def _table_after_heading(soup: BeautifulSoup, *keywords: str):
    """
    Find the first ``<table>`` that follows a heading containing all keywords.

    Searches in order: caption, h1..h4.  Stops search at the next same-level
    or higher-level heading.
    """
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "caption"]):
        heading_text = heading.get_text(" ", strip=True).lower()
        if not all(kw.lower() in heading_text for kw in keywords):
            continue
        # Found heading – look for next table sibling
        for sibling in heading.find_all_next():
            if sibling.name == "table":
                return sibling
            # Stop at next heading of same or higher level
            if sibling.name in ("h1", "h2", "h3", "h4") and sibling is not heading:
                break
    return None


# ---------------------------------------------------------------------------
# Federal section
# ---------------------------------------------------------------------------

def _parse_federal(soup: BeautifulSoup) -> dict:
    """
    Extract federal income tax brackets, BPAF min/max, and K1 rate.

    Returns::

        {
            "tax_brackets": [...],
            "bpaf": {"min": float, "max": float},
            "k1_rate": float,
        }
    """
    # --- Tax brackets ---
    table = None
    # Try several heading keyword combinations
    for kwds in [
        ("federal", "income tax"),
        ("federal", "tax"),
        ("federal", "net income"),
        ("federal",),
    ]:
        table = _table_after_heading(soup, *kwds)
        if table:
            break

    if table is None:
        # Last resort: find any table with a caption mentioning "federal"
        for t in soup.find_all("table"):
            cap = t.find("caption")
            if cap and "federal" in cap.get_text().lower():
                table = t
                break

    if table is None:
        raise ValueError("Could not locate federal tax bracket table in T4127 HTML")

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

    logger.warning("Could not parse BPAF from T4127 HTML; using K1-based fallback")
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
    from bs4 import BeautifulSoup as BS
    section_html = "".join(str(t) for t in section_tags)
    section_soup = BS(f"<div>{section_html}</div>", "lxml")

    # --- Tax brackets ---
    brackets: list[dict] = []
    for table in section_soup.find_all("table"):
        parsed = _parse_bracket_table(table)
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

def parse(session=None) -> dict:
    """
    Fetch and parse the CRA T4127 Payroll Deductions Formulas publication.

    Returns a dict with keys:
      - bpaf: {"min": float, "max": float}
      - k1_rate: float
      - tax_brackets: list[{"up_to": float|None, "rate": float}]
      - effective_date: str  (ISO date, e.g. "2026-01-01")
      - source_url: str
      - provinces: dict[str, {"bpa": float, "tax_brackets": [...]}]
    """
    import requests as _requests

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

    # 2. Fetch edition page → find document URL
    edition_html = _fetch(session, edition_url)
    doc_url = _find_document_url(edition_url, edition_html)

    # 3. Fetch the actual formulas document (may be same as edition page)
    if doc_url != edition_url:
        doc_html = _fetch(session, doc_url)
    else:
        doc_html = edition_html

    soup = BeautifulSoup(doc_html, "lxml")

    # 4. Effective date
    effective_date = _parse_effective_date(soup)
    if effective_date is None:
        from datetime import date
        effective_date = date.today().isoformat()
        logger.warning(
            "Could not parse effective date from T4127; falling back to today (%s)",
            effective_date,
        )

    # 5. Federal data (required — raises if missing)
    federal = _parse_federal(soup)

    # 6. Provincial data (best-effort)
    provinces = _parse_provinces(soup)
    if not provinces:
        logger.warning(
            "T4127 parser returned no provincial data — "
            "the document structure may have changed"
        )

    return {
        "bpaf": federal["bpaf"],
        "k1_rate": federal["k1_rate"],
        "tax_brackets": federal["tax_brackets"],
        "effective_date": effective_date,
        "source_url": doc_url,
        "provinces": provinces,
    }
