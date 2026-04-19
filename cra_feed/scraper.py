"""CRA payroll tax feed scraper entry point.

Run with:
    python -m cra_feed.scraper

Writes the following files (relative to the repo root):
    cra_feed/output/v1/ca/latest.json
    cra_feed/output/v1/ca/<effective_date>.json   e.g. 2026-01-01.json
    cra_feed/output/v1/ca/index.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from cra_feed.parsers import cpp_ei, t4127
from cra_feed.schema import (
    BPAFRange,
    CPP2Data,
    CPPData,
    CRAFeed,
    EIData,
    FederalData,
    ProvinceData,
    TaxBracket,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "cra_feed" / "output" / "v1" / "ca"
CACHE_DIR = REPO_ROOT / "cra_feed" / "cache"

USER_AGENT = (
    "maplehornconsulting-art-cra-feed/0.1 "
    "(+https://github.com/maplehornconsulting-art/payroll)"
)
REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _cached_get(session: requests.Session, url: str) -> str:
    """Fetch *url*, caching the raw HTML under CACHE_DIR keyed by URL hash."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    cache_file.write_text(response.text, encoding="utf-8")
    return response.text


def _canonical_checksum(data: dict) -> str:
    """Return SHA-256 of the canonical (sorted-keys, checksum_sha256='') JSON."""
    payload = {**data, "checksum_sha256": ""}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Build feed
# ---------------------------------------------------------------------------

def build_feed() -> CRAFeed:
    session = _make_session()

    t4127_data = t4127.parse(session)
    cpp_ei_data = cpp_ei.parse(session)

    effective_date: str = t4127_data["effective_date"]
    published_at: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    source_urls = [
        t4127_data["source_url"],
        *cpp_ei_data["source_urls"],
    ]

    federal = FederalData(
        bpaf=BPAFRange(**t4127_data["bpaf"]),
        k1_rate=t4127_data["k1_rate"],
        tax_brackets=[TaxBracket(**b) for b in t4127_data["tax_brackets"]],
    )

    cpp = CPPData(**cpp_ei_data["cpp"])
    cpp2 = CPP2Data(**cpp_ei_data["cpp2"])
    ei = EIData(**cpp_ei_data["ei"])

    # Provincial data comes from the T4127 publication
    provinces = {
        code: ProvinceData(
            bpa=pdata["bpa"],
            tax_brackets=[TaxBracket(**b) for b in pdata["tax_brackets"]],
        )
        for code, pdata in t4127_data.get("provinces", {}).items()
    }

    if not provinces:
        logger.warning(
            "No provincial data was parsed from the T4127 publication — "
            "the feed will lack provincial tax brackets."
        )

    # Build the raw dict first so we can compute the checksum.
    raw: dict = {
        "schema_version": "1.0",
        "jurisdiction": "CA",
        "effective_date": effective_date,
        "published_at": published_at,
        "source_urls": source_urls,
        "federal": federal.model_dump(),
        "cpp": cpp.model_dump(),
        "cpp2": cpp2.model_dump(),
        "ei": ei.model_dump(),
        "provinces": {k: v.model_dump() for k, v in provinces.items()},
        "checksum_sha256": "",  # placeholder — filled below
    }

    raw["checksum_sha256"] = _canonical_checksum(raw)

    # Validate with Pydantic before writing.
    feed = CRAFeed.model_validate(raw)
    return feed


# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------

def write_outputs(feed: CRAFeed) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    feed_dict = feed.model_dump()

    def _write(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  Wrote {path.relative_to(REPO_ROOT)}")

    latest_path = OUTPUT_DIR / "latest.json"
    dated_path = OUTPUT_DIR / f"{feed.effective_date}.json"

    _write(latest_path, feed_dict)
    _write(dated_path, feed_dict)

    # Update index.json
    index_path = OUTPUT_DIR / "index.json"
    index: list[dict] = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = []

    dated_bytes = json.dumps(feed_dict, indent=2, ensure_ascii=False).encode()
    dated_sha = hashlib.sha256(dated_bytes).hexdigest()

    # Replace or append entry for this effective_date.
    entry = {
        "effective_date": feed.effective_date,
        "published_at": feed.published_at,
        "sha256": dated_sha,
        "file": f"{feed.effective_date}.json",
    }
    index = [e for e in index if e.get("effective_date") != feed.effective_date]
    index.append(entry)
    index.sort(key=lambda e: e["effective_date"])

    _write(index_path, index)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("CRA Feed Scraper starting …")
    feed = build_feed()
    write_outputs(feed)
    print(f"Done. effective_date={feed.effective_date}  checksum={feed.checksum_sha256[:16]}…")


if __name__ == "__main__":
    main()
