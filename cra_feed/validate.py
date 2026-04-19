"""JSON Schema validation for the CRA payroll tax feed (v1).

Usage as a library::

    from cra_feed.validate import validate_feed
    validate_feed(feed_dict)   # raises jsonschema.ValidationError on failure

Usage from the command line::

    python -m cra_feed.validate path/to/feed.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "v1.schema.json"


def load_schema() -> dict:
    """Load and return the v1 JSON Schema as a dict."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_feed(feed_dict: dict) -> None:
    """Validate *feed_dict* against the v1 JSON Schema.

    Raises :exc:`jsonschema.ValidationError` if validation fails.
    The error is allowed to bubble up so that callers (including the scraper
    and the GitHub Actions workflow) exit non-zero automatically.
    """
    schema = load_schema()
    jsonschema.validate(instance=feed_dict, schema=schema)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python -m cra_feed.validate <path-to-feed.json>", file=sys.stderr)
        sys.exit(1)

    feed_path = Path(sys.argv[1])
    if not feed_path.exists():
        print(f"Error: file not found: {feed_path}", file=sys.stderr)
        sys.exit(1)

    try:
        feed = json.loads(feed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {feed_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        validate_feed(feed)
        print(f"OK: {feed_path} is valid.")
    except jsonschema.ValidationError as exc:
        print(f"Validation error in {feed_path}:\n  {exc.message}", file=sys.stderr)
        print(f"  Path: {list(exc.absolute_path)}", file=sys.stderr)
        sys.exit(1)
