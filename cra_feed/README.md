# CRA Payroll Tax Feed — `cra_feed/`

> **⚠ Disclaimer:** This feed is **not** an official product of the Canada Revenue Agency (CRA) or the Government of Canada. Values are derived from publicly available CRA publications and are provided for convenience only. All payroll calculations **must be reviewed and approved by a qualified Canadian payroll professional** before being applied to live payroll. No warranty of any kind is provided.

---

## What this feed is

A free, zero-cost, machine-readable JSON feed of Canadian federal and provincial payroll tax data, published under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada). It is updated automatically via a daily GitHub Actions workflow and hosted on GitHub Pages — no server required.

**Primary scope:** Federal values + all provinces/territories **except Quebec** (matching `l10n_ca_hr_payroll_except_QC`).

## What this feed is not

- It is **not** an official CRA service or API.
- It is **not** a substitute for professional payroll advice.
- It does **not** cover Quebec (Revenu Québec data is out of scope).
- It is **not** guaranteed to be current at the exact moment you read this — the automated scraper runs daily, but CRA pages can change without notice.

---

## Licence

Feed **contents** are derived from canada.ca content released under the  
**[Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada)**.  
Attribution preserved: © His Majesty the King in Right of Canada, as represented by the Minister of National Revenue.

Feed **code** (the Python scraper, workflow, and schema) is MIT-licensed.

---

## Public feed URL

```
https://maplehornconsulting-art.github.io/payroll/v1/ca/latest.json
https://maplehornconsulting-art.github.io/payroll/v1/ca/<effective_date>.json
https://maplehornconsulting-art.github.io/payroll/v1/ca/index.json
```

---

## How to enable GitHub Pages

1. Go to **Settings → Pages** in the `maplehornconsulting-art/payroll` repository.
2. Under **Source**, select **GitHub Actions**.
3. Run the workflow once manually: **Actions → Scrape CRA & Publish Feed → Run workflow**.
4. The feed will be live at `https://maplehornconsulting-art.github.io/payroll/`.

---

## How to add GPG signing (optional)

1. Generate a GPG key pair (or export an existing one):
   ```bash
   gpg --export-secret-keys --armor YOUR_KEY_ID > cra_feed_key.asc
   ```
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `CRA_FEED_GPG_KEY`
   - Value: paste the contents of `cra_feed_key.asc`
3. On subsequent runs the workflow will produce a `.sig` detached signature beside each JSON file.

---

## JSON feed schema (v1)

`latest.json` shape:

```json
{
  "schema_version": "1.0",
  "jurisdiction": "CA",
  "effective_date": "2026-07-01",
  "published_at": "2026-04-18T06:00:00Z",
  "source_urls": [
    "https://www.canada.ca/.../t4127-...html",
    "https://www.canada.ca/.../cpp-contribution-rates.html"
  ],
  "federal": {
    "bpaf": { "min": 14538.00, "max": 16129.00 },
    "k1_rate": 0.15,
    "tax_brackets": [
      { "up_to": 57375.00, "rate": 0.15 },
      { "up_to": 114750.00, "rate": 0.205 },
      { "up_to": 158519.00, "rate": 0.26 },
      { "up_to": 220000.00, "rate": 0.29 },
      { "up_to": null,      "rate": 0.33 }
    ]
  },
  "cpp": { "rate": 0.0595, "ympe": 71300, "basic_exemption": 3500 },
  "cpp2": { "rate": 0.04, "yampe": 81900 },
  "ei":  { "rate": 0.0166, "max_insurable_earnings": 65700 },
  "provinces": {
    "ON": { "bpa": 11865, "tax_brackets": [ … ] },
    "BC": { "bpa": 11981, "tax_brackets": [ … ] }
  },
  "checksum_sha256": "<hex of canonical JSON of this object minus this field>"
}
```

### Field descriptions

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Feed schema version (`"1.0"`) |
| `jurisdiction` | string | Always `"CA"` |
| `effective_date` | string | CRA effective date (ISO 8601, e.g. `"2026-07-01"`) |
| `published_at` | string | UTC timestamp when this file was generated |
| `source_urls` | array | CRA pages used as data sources |
| `federal.bpaf.min` | number | Federal basic personal amount at lower net income threshold |
| `federal.bpaf.max` | number | Federal basic personal amount at full amount |
| `federal.k1_rate` | number | Lowest federal tax rate (used to compute K1 non-refundable tax credit) |
| `federal.tax_brackets` | array | Federal income tax brackets; `up_to: null` = top bracket |
| `cpp.rate` | number | Employee CPP contribution rate |
| `cpp.ympe` | number | Year's Maximum Pensionable Earnings |
| `cpp.basic_exemption` | number | Annual basic CPP exemption |
| `cpp2.rate` | number | Employee CPP2 contribution rate |
| `cpp2.yampe` | number | Year's Additional Maximum Pensionable Earnings |
| `ei.rate` | number | Employee EI premium rate |
| `ei.max_insurable_earnings` | number | Maximum insurable earnings for EI |
| `provinces.<code>.bpa` | number | Provincial/territorial basic personal amount |
| `provinces.<code>.tax_brackets` | array | Provincial tax brackets |
| `checksum_sha256` | string | SHA-256 of canonical JSON (keys sorted, this field = `""`) |

---

## Fetch & verify with curl

```bash
# Fetch the latest feed
curl -fsSL https://maplehornconsulting-art.github.io/payroll/v1/ca/latest.json \
     -o latest.json

# Verify the built-in checksum (Python one-liner)
python3 - <<'EOF'
import json, hashlib
data = json.load(open("latest.json"))
claimed = data.pop("checksum_sha256", "")
canonical = json.dumps({**data, "checksum_sha256": ""}, sort_keys=True, separators=(",",":"))
computed = hashlib.sha256(canonical.encode()).hexdigest()
print("OK" if computed == claimed else f"MISMATCH  claimed={claimed}  computed={computed}")
EOF

# (Optional) Verify GPG signature
curl -fsSL https://maplehornconsulting-art.github.io/payroll/v1/ca/latest.json.sig \
     -o latest.json.sig
gpg --verify latest.json.sig latest.json
```

---

## How the Odoo connector will consume this feed

A follow-up Odoo module (`l10n_ca_hr_payroll_cra_connector`) will:
1. Fetch `latest.json` from the URL above using `requests` within an `ir.cron` job.
2. Verify `checksum_sha256` before trusting the data.
3. Optionally verify the GPG detached signature.
4. Create a draft `cra.tax.update` record for a payroll admin to review.
5. On approval, write the new values into `hr.rule.parameter` records with the correct `effective_date`.

---

## Maintenance schedule

CRA publishes payroll updates effective **January 1** and **July 1** each year.

- Parsers in `cra_feed/parsers/` should be reviewed and updated at least **2 weeks before each effective date** (i.e., by mid-December and mid-June).
- The GitHub Actions workflow runs daily; if any CRA page structure changes, the run will fail and GitHub will send a failure notification email.
- Check the Actions tab for run history and failures.

---

## Running locally

```bash
# Install dependencies
pip install -r cra_feed/requirements.txt

# Run the scraper
python -m cra_feed.scraper

# Output files will appear under:
#   cra_feed/output/v1/ca/latest.json
#   cra_feed/output/v1/ca/<effective_date>.json
#   cra_feed/output/v1/ca/index.json
```

The scraper caches raw HTML responses under `cra_feed/cache/` (git-ignored). Delete the cache to force a fresh fetch.
