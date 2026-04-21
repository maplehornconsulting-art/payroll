# Canada Payroll — All Provinces & Territories (Except Quebec)

## Compatibility

| | |
|---|---|
| **Odoo Edition** | Enterprise (required) |
| **Minimum Version** | 18.0 |
| **Python** | 3.10+ |
| **Dependencies** | `hr_payroll`, `hr_payroll_account`, `l10n_ca`, `hr_work_entry_holidays`, `hr_payroll_holidays` |

## Short Description

Complete Canadian payroll module with CPP/CPP2, EI, federal tax, provincial tax for all provinces/territories (except Quebec), Ontario Health Premium, RRSP, and Union Dues — fully compliant with 2025/2026 CRA rates.

---

## Overview

**Canada Payroll** is a comprehensive, production-ready payroll localization module for Odoo. It automates the calculation of all mandatory Canadian payroll deductions — CPP, CPP2, EI, federal income tax, and provincial/territorial income tax — for every province and territory except Quebec.

Built for Canadian businesses of all sizes, this module eliminates manual payroll calculations, reduces compliance risk, and integrates seamlessly with Odoo's native Payroll, Employees, and Leave Management apps.

Developed by **MapleHorn Consulting Inc.** — Canadian payroll experts.

---

## Key Features

### 🇨🇦 Federal Deductions
- **CPP (Canada Pension Plan)** — Employee & employer contributions with YMPE limits, basic exemption, and annual maximums
- **CPP2 (Second Additional CPP)** — Automatic calculation for earnings above YMPE up to the CPP2 ceiling
- **EI (Employment Insurance)** — Employee premiums and employer contributions (1.4× multiplier)
- **Federal Income Tax** — 5-bracket progressive tax with Basic Personal Amount (BPA) phase-out configurable per contract (default OFF to match PDOC)
- **Additional Federal Tax** — Support for employee-requested additional withholding (TD1 Section 2)

### 🏢 Pay Structure Types — Hourly & Salaried
Two structure types are included out of the box so an admin can simply assign the right one when creating a contract:

| Structure Type | `wage_type` | Use for |
|---|---|---|
| **Canadian Employee — Hourly** | `hourly` | Contracts that pay by attendance hours × `hourly_wage` |
| **Canadian Employee — Salaried** | `monthly` | Contracts that pay a fixed `wage` per period |

Both structure types use the same full rule set (CPP/CPP2, EI, Federal Tax, Provincial Tax, OHP, etc.) and support all pay schedules (weekly, bi-weekly, semi-monthly, monthly, etc.).

### 🏛️ Provincial/Territorial Tax — All 12 Jurisdictions
Dynamic province detection from the employee record. One salary structure works for all provinces:

| Province/Territory | Brackets | Surtax | Health Premium |
|---|---|---|---|
| Ontario (ON) | 5 | ✅ 20% + 36% | ✅ OHP ($0–$900) |
| Alberta (AB) | 6 | — | — |
| British Columbia (BC) | 7 | — | — |
| Saskatchewan (SK) | 3 | — | — |
| Manitoba (MB) | 3 | — | — |
| New Brunswick (NB) | 4 | — | — |
| Nova Scotia (NS) | 5 | — | — |
| Prince Edward Island (PE) | 5 | — | — |
| Newfoundland & Labrador (NL) | 8 | — | — |
| Northwest Territories (NT) | 4 | — | — |
| Yukon (YT) | 5 | — | — |
| Nunavut (NU) | 4 | — | — |

### 💰 Pre-Tax Deductions
- **RRSP Deduction** — Reduces taxable income before federal and provincial tax (does not reduce CPP/EI per CRA rules)
- **Union Dues** — Pre-tax deduction with proper tax treatment

### 📊 Salary Inputs
- Overtime (OT)
- Bonus
- Commission
- RRSP Deduction
- Union Dues

### 🔧 Employee Configuration
- Social Insurance Number (SIN) with masked display on payslips
- Federal TD1 Claim Code (Codes 0–10)
- Province of Employment selector (drives all provincial tax calculations)
- CPP Exempt flag
- EI Exempt flag
- Additional Federal Tax withholding amount

### 📄 Payslip Report
- Professional pay stub template
- Organized sections: Earnings, Deductions, Net Pay, Employer Contributions
- SIN masked for privacy (shows only last 3 digits)
- Province of employment displayed

### 📐 Calculation Rules (Per CRA Guidelines)
- **Bi-weekly (26 pay periods/year)** payroll cycle
- CPP/EI calculated on **gross earnings** (not reduced by RRSP/Union)
- Federal & provincial tax calculated on **taxable income** (after RRSP/Union)
- **Federal BPA phase-out (configurable per contract; default OFF to match PDOC)** — between Bracket 3 and Bracket 4 for high earners
- Ontario surtax on basic provincial tax exceeding thresholds
- Ontario Health Premium based on annual taxable income tiers
- All amounts properly annualized and de-annualized

---

## Payslip Computation Flow

```
BASIC (wage) → GROSS (+ OT, Bonus, Commission)
    → RRSP Deduction (if entered)
    → Union Dues (if entered)
    → CPP Employee (on GROSS)
    → CPP2 Employee (on GROSS above YMPE)
    → EI Employee (on GROSS)
    → Federal Income Tax (on taxable income)
    → Provincial Income Tax (on taxable income, province-specific)
    → Ontario Health Premium (Ontario only)
    → NET SALARY
    → CPP Employer (mirrors employee)
    → CPP2 Employer (mirrors employee)
    → EI Employer (1.4× employee premium)
```

---

## 2025/2026 Tax Rates Included

### Federal
| Bracket | Threshold | Rate |
|---|---|---|
| 1 | $0 – $58,523 | 14.0% |
| 2 | $58,523 – $117,045 | 20.5% |
| 3 | $117,045 – $181,440 | 26.0% |
| 4 | $181,440 – $258,482 | 29.0% |
| 5 | Over $258,482 | 33.0% |
| BPA Max | $16,452 | — |
| BPA Min | $14,829 | — |

### CPP / CPP2 / EI
| Parameter | Value |
|---|---|
| CPP Rate | 5.95% |
| CPP YMPE | $74,600 |
| CPP Basic Exemption | $3,500 |
| CPP Max Contribution | $4,230.45 |
| CPP2 Rate | 4.00% |
| CPP2 Ceiling | $85,000 |
| CPP2 Max Contribution | $416.00 |
| EI Employee Rate | 1.63% |
| EI Max Insurable | $68,900 |
| EI Max Premium | $1,123.07 |
| EI Employer Multiplier | 1.4× |

---

## Accounting Integration

This module integrates with **Odoo Accounting** (`hr_payroll_account`).
When a payslip is confirmed, a balanced `account.move` is created in the
**Salary Journal** (`SAL`).

### Canadian GL Accounts

The following accounts are created automatically on install (one set per
Canadian company):

| Code | Name | Type |
|---|---|---|
| 2310 | CRA Source Deductions Payable — Federal Income Tax | Liability |
| 2320 | CRA Source Deductions Payable — CPP | Liability |
| 2321 | CRA Source Deductions Payable — CPP2 | Liability |
| 2330 | CRA Source Deductions Payable — EI | Liability |
| 2340 | Provincial Income Tax Withheld Payable | Liability |
| 2350 | Ontario EHT Payable | Liability |
| 2360 | RRSP Contributions Payable | Liability |
| 2370 | Union Dues Payable | Liability |
| 2380 | Net Pay Clearing | Liability |
| 5410 | Salaries & Wages Expense | Expense |
| 5420 | CPP Employer Contribution Expense | Expense |
| 5421 | CPP2 Employer Contribution Expense | Expense |
| 5430 | EI Employer Premium Expense | Expense |

Accounts 5411 (PTO), 5412 (Sick), 5413 (OT), 5440 (EHT) are created for
future granular expense tracking / EHT employer rule support.

### CRA PD7A Reconciliation

After the module is installed, the credit balances on accounts 2310–2340
represent exactly what must be remitted to CRA and the province on your
PD7A form:

- **2310** → Federal income tax withheld (Line 1)
- **2320** → CPP — employee + employer contributions (Line 2)
- **2330** → EI — employee + 1.4× employer premiums (Line 3)
- **2340** → Provincial income tax + Ontario Health Premium

### Overriding Account Mapping

To use different GL accounts for your company, go to:

> **Payroll → Configuration → Salary Rules** → open a rule → change the
> **Debit Account** / **Credit Account** fields.

### Quebec Exclusion

This module is `_except_QC` by design.  No QPP, QPIP, HSF, CNESST, or Revenu
Québec accounts are created here.

See [`docs/ACCOUNTING.md`](docs/ACCOUNTING.md) for the full debit/credit table
and a worked payslip example.

---

## Remittances & Annual Reporting

Starting with **v19.0.2.0**, the module includes a complete Canadian payroll
remittance workflow directly alongside the payroll computation and GL posting
features.

### 🏦 Remittance Workflow

1. **Remittance Configuration** — set your CRA remitter type, Business Number,
   WCB/EHT account numbers, and default bank journal per company.
2. **Auto-creation (daily cron)** — draft `Remittance` records are created
   automatically each day for applicable periods.
3. **Review & Confirm** — review aggregated liability balances, print the
   PD7A Voucher PDF, then click **Confirm** to lock the record and generate
   the clearing journal entry.
4. **Register Payment** — the payment wizard creates an `account.payment` to
   the Receiver General, posts the journal entry, and reconciles the clearing
   account.

### 📊 Annual Reporting Dashboard

Access via **Payroll → Year-End Reporting**:

| Menu Item | Purpose |
|---|---|
| **Owing Now** | All unpaid/unconfirmed remittances — quick view of open liabilities |
| **Remittances** | Full list, searchable/filterable, grouped by type with totals |
| **Overdue Remittances** | Kanban of past-due remittances (highlighted red) |
| **Remittance Configuration** | Manager-only config per company |

### ✅ T4 ↔ PD7A Annual Reconciliation

Call `get_t4_reconciliation(year=2026)` on the `l10n.ca.remittance` model to
compare paid PD7A remittances against T4 box totals (Box 16 CPP + Box 18 EI
+ Box 22 Federal Tax).  The widget returns `match=True` when the delta is
within $1.00 — matching CRA's T4 Summary Box 82 cross-check.

See [`docs/REMITTANCES.md`](docs/REMITTANCES.md) for the full remittance
workflow documentation, due-date schedule, and reconciliation guide.

---

## Compatibility

| | Version |
|---|---|
| **Odoo Edition** | Enterprise |
| **Odoo Version** | 18.0 |
| **Python** | 3.10+ |
| **Dependencies** | `hr_payroll`, `hr_payroll_account`, `l10n_ca`, `hr_work_entry_holidays`, `hr_payroll_holidays` |

---

## Installation

### Method: Odoo.sh / Self-Hosted

1. Download the module and extract to your Odoo addons directory:
   ```
   /your-odoo/addons/l10n_ca_hr_payroll/
   ```

2. Update the module list:
   - Go to **Apps** → click **Update Apps List**

3. Search and install:
   - Search for **"Canada - Payroll"**
   - Click **Install**

---

## Configuration

### Step 1: Set Up Employees

1. Go to **Employees** → select an employee
2. Navigate to the **Canadian Payroll** tab
3. Fill in:
   - **SIN** (Social Insurance Number)
   - **Federal TD1 Claim Code** (default: Code 1)
   - **Province of Employment** ← This drives provincial tax calculation

### Step 2: Configure Contracts

1. Go to the employee's **Contract** (via Payroll settings)
2. Set:
   - **Wage** — hourly rate for hourly employees, monthly/bi-weekly amount for salaried employees
   - **Structure Type** → select the appropriate type:
     - **Canadian Employee — Hourly**: contracts that pay by attendance hours × `hourly_wage`
     - **Canadian Employee — Salaried**: contracts that pay a fixed `wage` per period
   - **CPP Exempt** / **EI Exempt** if applicable
   - **Additional Federal Tax** (if employee requested on TD1)

### Step 3: Create Payslips

1. Go to **Payroll** → **Payslips** → **Create**
2. Select the employee and pay period
3. (Optional) Add salary inputs:
   - Overtime, Bonus, Commission, Vacation Pay
   - RRSP Deduction, Union Dues
4. Click **Compute Sheet**
5. Review and **Confirm**

---

## Updating Tax Rates Yearly

All tax parameters are stored as **dated rule parameters** (`hr.rule.parameter.value`). To update for a new tax year:

1. Go to **Payroll** → **Configuration** → **Rule Parameters**
2. Find the parameter (e.g., "Canada - CPP Employee Rate")
3. Add a new value with the new `date_from` and updated amount

Provincial brackets are stored in the `l10n_ca_prov_tax_config` rule parameter (one JSON blob for all provinces). The CRA Connector module updates this parameter automatically each year. To update manually, go to **Payroll → Configuration → Rule Parameters** and edit "Canada - Provincial Tax Config (All Provinces)". The `PROV_TAX` salary rule also contains an embedded 2026 fallback that is used when the parameter is absent.

---

## What's NOT Included (Quebec)

This module does **not** support Quebec. Quebec has a separate payroll system:
- QPP (Quebec Pension Plan) instead of CPP
- QPIP (Quebec Parental Insurance Plan)
- Reduced EI rate
- Revenu Québec provincial tax (separate filing)
- RL-1 slip instead of T4

A future `l10n_ca_qc_hr_payroll` module may be developed for Quebec.

---

## Support

| | |
|---|---|
| **Author** | MapleHorn Consulting Inc. |
| **Website** | www.maplehornconsulting.com |
| **Email** | info@maplehornconsulting.com |
| **License** | OPL-1 (Odoo Proprietary License) |

---

## Changelog

### v1.11 (April 2026) — Replaced runtime clone with explicit XML declarations for the Salaried structure

**Root cause:** Any runtime "clone Hourly rules into Salaried" strategy is
architecturally fragile. It depends on category load order, xmlid resolution,
and `Rule.create()` not raising on any of ~12 rules. One swallowed exception
→ the user sees a blank Salaried payslip. This applied on fresh install, and
again on every uninstall + reinstall cycle.

**Fix:** Replaced the entire clone-at-runtime approach with explicit XML
declarations for both structures, mirroring how Odoo's own `l10n_be_hr_payroll`
and `l10n_us_hr_payroll` modules ship multiple structures.

- ✅ Every CA salary rule is now declared **twice** in `hr_salary_rule_data.xml`:
  once for the Hourly structure, once for the Salaried structure (suffix `_salaried`).
- ✅ Both records share an identical `amount_python_compute` one-liner that calls
  a `_l10n_ca_compute_*` helper method on `hr.payslip`. The actual math lives
  in Python in a single place and is never duplicated.
- ✅ All clone-related code deleted: `_l10n_ca_clone_rules_to_salaried`,
  `_CLONE_FIELDS`, `_REPAIR_FIELDS`, the `<function>` tag, and the clone trigger
  in `post_init_hook`.
- ✅ A diagnostic `_register_hook` is kept on `hr.payroll.structure` that **only
  logs** a comparison of rule counts at server startup — it never mutates data.
- ✅ Works on fresh install, upgrade, uninstall+reinstall — no manual intervention.
- ⚠️  Run `-u l10n_ca_hr_payroll_except_QC` when upgrading from v1.10.

### v1.9 (April 2026) — Configurable Federal BPA phase-out

- ✅ New per-contract Boolean `l10n_ca_apply_bpa_phase_out` (default **OFF**).
- ✅ Default behavior now matches CRA PDOC, Wave, QuickBooks, ADP, and Ceridian
     for high earners — no more ~$8/period over-withhold mismatch with PDOC.
- ✅ Customers wanting strict CRA T4127 §5.1 conformance can flip the checkbox
     **ON** per contract.
- ✅ Four regression tests: NS $10k biweekly phase-out OFF (≈$2,146.45 PDOC), phase-out ON
     (≈$2,155.09 pre-v1.9), $2k biweekly unchanged, $300k/yr difference = (bpa_max−bpa_min)×0.14/26.
- ⚠️  **Behavior change for high earners** (annual taxable income > $181,440): federal tax
     withheld will drop slightly with the new default. No CRA penalty exposure — the
     employee reconciles on their T1 filing.
- ⚠️  Run `-u l10n_ca_hr_payroll_except_QC` to add the new field.

#### BPA phase-out trade-off

At high incomes (annual taxable income $181,440–$258,482), CRA T4127 §5.1 phases the
federal BPA from $16,452 down to $14,829. This is letter-of-the-law correct, but CRA
PDOC and most major Canadian payroll products (Wave, QuickBooks, ADP, Ceridian) do
**not** apply this phase-out — they honor the TD1 amount verbatim.

| Approach | Annual K1 | Annual fed tax | Per-period (26×) |
|---|---|---|---|
| Phase-out ON (T4127 §5.1) | phased BPA × 0.14 | higher | **≈ $2,155.09** |
| Phase-out OFF (PDOC/default) | (BPA_MAX + CEA) = $17,952 × 0.14 = $2,513.28 | lower | **≈ $2,146.45** |

Both approaches are CRA-acceptable. Phase-out ON causes over-withholding (~$224/yr for a
$10,000 biweekly earner); phase-out OFF causes slight under-withholding that the employee
reconciles on their T1 filing. There is no CRA penalty risk in either direction.

### v1.10 (April 2026) — Salaried structure clone hardening & silent-drop fix

**Root cause:** Rules like `BASIC`, `GROSS`, and `NET` were silently dropped from
the Salaried structure when `Rule.create()` raised an exception because a
`category_id` (or other Many2one field) referenced a record that was no longer
accessible (deleted, not yet loaded, or inaccessible due to ACL). The exception
was caught and logged only at WARNING level, leaving the Salaried structure
incomplete. Without `BASIC` and `GROSS`, every downstream rule (`CPP_EE`,
`EI_EE`, `FED_TAX`, `PROV_TAX`, `NET`, …) computed zero, making Salaried
payslips appear empty.

- ✅ **Dangling many2one validation** — before calling `Rule.create()`, the clone
  pass now checks `category_id` and `parent_rule_id` with `.exists()`. If the
  referenced record no longer exists, the field is cleared to `False` (and a
  `WARNING` is logged) so the rule is still created instead of being silently lost.
- ✅ **Full-traceback ERROR logging** — clone failures now log at `ERROR` level
  with the full Python traceback (`traceback.format_exc()`) and a summary of the
  `vals` dict (excluding large `amount_python_compute` / `condition_python` blobs),
  making self-diagnosis possible without a support ticket.
- ✅ **`failed_codes` tracking** — rules that fail `create()` are collected in a
  `failed_codes` list so the count of failures is visible in the post-clone
  summary log.
- ✅ **`_register_hook` INFO log** — on every server start, an `INFO` line now
  reports the rule count for both Hourly and Salaried structures (previously only
  logged at `DEBUG`). If counts differ, an `ERROR` is also logged listing the
  missing rule codes.
- ✅ **`_register_hook` auto-heal** — when missing rules are detected at startup
  and `registry.ready` is `True`, the clone/repair pass is automatically re-run,
  so any server restart after a `-u l10n_ca_hr_payroll_except_QC` fully restores
  the Salaried structure without manual intervention.
- ✅ **New regression tests** (`test_salaried_parity.py`) — 12 pure-Python tests
  covering the bug scenario (BASIC/GROSS/NET silently missing when category
  dangling) and the fix (dangling ref cleared → rule successfully cloned).
  Two "bug demonstration" tests verify the old behaviour was broken; ten "fix
  validation" tests verify the new behaviour is correct.
- ⚠️ **Action required on existing databases**: run `-u l10n_ca_hr_payroll_except_QC`
  (or simply restart the Odoo server after the upgrade). The auto-heal logic in
  `_register_hook` will detect and repair any missing Salaried rules automatically.

### v1.8 (April 2026) — High-earner U1 income deduction fix

- ✅ **Bug fix — FED_TAX & PROV_TAX: U1 (enhanced CPP income deduction) no longer capped**: Per CRA T4127 §5.2, the U1 income deduction must be computed as *per-period enhanced CPP × pay periods* with **no annual cap**. The previous code used `_l10n_ca_projected_annual_contribution` (which caps at the annual CPP maximum of $4,230.45) for both U1 and K2/K2P, overstating taxable income by up to $813/year for high earners (gross > ~$2,734 biweekly). At $6,000 biweekly (NS), this caused Federal tax to be over-withheld by $8.12/period and Provincial tax by $5.48/period.
- ✅ **K2/K2P credits unchanged** — the `_l10n_ca_projected_annual_contribution` helper (capped) is still used for the base CPP and EI non-refundable credits, as these reflect actual employee contributions.
- ✅ Added inline comments in both `salary_rule_ca_fed_tax` and `salary_rule_ca_prov_tax` citing CRA T4127 §5.2 to explain the intentional cap/uncap distinction, preventing future regressions.
- ✅ New regression tests: NS @ $4,000 biweekly (Fed ≈$544.11, Prov ≈$491.66) and NS @ $6,000 biweekly (Fed $1,029.20, Prov $838.16, CPP $348.99, EI $97.80, Net $3,685.85) — all matching CRA PDOC within ±$0.10.
- ✅ Updated `_fed_tax` and `_prov_tax` test formula helpers to mirror the corrected uncapped U1 logic.
- ⚠️ **Upgrade required**: run `-u l10n_ca_hr_payroll_except_QC` on existing databases so the corrected FED_TAX and PROV_TAX salary rules take effect on newly computed payslips. Previously confirmed payslips are unaffected.

### v1.6 (April 2026) — EI cap fix, CPP2 YTD-based triggering

- ✅ **Bug #1 — EI per-period insurable cap removed**: EI premium is now computed as `gross × rate` (T4127 §4.1). The old code incorrectly capped insurable earnings at `ei_max_insurable / periods` per period, producing an EI of $43.20 instead of the correct $65.20 at $4,000 biweekly. The annual maximum premium (`ei_max_premium`) remains the only cap.
- ✅ **Bug #2 — CPP2 triggers by YTD pensionable earnings, not per-period YMPE**: CPP2 now applies only when the employee's cumulative pensionable earnings for the year exceed the annual YMPE ($74,600). The old code prorated YMPE per period (`YMPE / periods`), incorrectly charging CPP2 from pay #1 for high earners. At $4,000 biweekly, CPP2 correctly starts at pay #20 (when YTD pensionable crosses $74,600).
- ✅ **New helper `_l10n_ca_ytd_pensionable_earnings()`** on `hr.payslip` — sums pensionable earnings from prior confirmed payslips in the same calendar year (used internally by the CPP2_EE rule).
- ⚠️  **Upgrade required**: run `-u l10n_ca_hr_payroll_except_QC` on existing databases so the updated CPP2_EE and EI_EE salary rules take effect on newly computed payslips.

### v1.5 (April 2026) — Salaried structure parity

- ✅ Replaced `rule.copy()` with explicit field-by-field clone in `_l10n_ca_clone_rules_to_salaried` — fixes missing accounting integration (`account_debit`, `account_credit`) on salaried payslips
- ✅ Repair pass in `_l10n_ca_clone_rules_to_salaried` — on upgrade, fills in missing `account_debit` / `account_credit` / python compute on existing salaried rules created by the old buggy clone, so `-u l10n_ca_hr_payroll_except_QC` is enough to fix production databases without manually deleting and recreating salaried rules
- ✅ `_get_paid_amount` non-CA fallback: function now always returns a numeric value (never `None`) for non-Canadian payslips
- ✅ `_get_paid_amount` monthly wage_type scaling: salaried employees on non-monthly schedules (e.g. bi-weekly) now receive the correct per-period BASIC amount (base × 12 / periods) instead of the full monthly wage
- ⚠️  **Upgrade required**: run `-u l10n_ca_hr_payroll_except_QC` on existing databases so the salaried structure rules are re-cloned with full accounting field values

### v2.0 (April 2026) — Remittances & Annual Reporting

- ✅ Added full Canadian payroll remittance workflow inside the module
- ✅ Remittance configuration per company (CRA remitter type, BN, WCB, EHT)
- ✅ Daily cron auto-creates draft `l10n.ca.remittance` records per CRA schedule
- ✅ Due-date computation for all remitter types with weekend rollover
- ✅ Liability account aggregation from posted payslip journal entries
- ✅ Confirm → journal entry; Pay → `account.payment` to Receiver General
- ✅ Annual dashboard: Owing Now, This Year's Remittances, Late Warnings
- ✅ T4 ↔ PD7A annual reconciliation widget (match within $1 = green ✓)
- ✅ PD7A Remittance Voucher PDF (QWeb) with itemized breakdown
- ✅ Optional PD7A CSV export (draft CRA format)
- ✅ Idempotent post_init_hook creates CRA partner + RemittanceConfig per company

### v1.7 (April 2026) — OHP rate fix & Salaried structure hardening
- ✅ **Fixed Ontario Health Premium (OHP) rate in tiers 4–5** (`0.0025` → `0.25`): corrects a 100× error that understated OHP by ~$4/period for most Ontario employees. Annual OHP now stair-steps correctly: $0 → $300 → $450 → $600 → $900 per T4127 Ch 6 §6.7
- ✅ OHP fix applied in both `hr_rule_parameters_data.xml` (live rule parameter) and the `OHP_CFG` fallback dict in `hr_salary_rule_data.xml`
- ✅ **Salaried structure clone robustness**: clone/repair failures now log at ERROR level (was WARNING) so they are visible in standard server logs
- ✅ Added post-clone final-state assertion: logs ERROR with missing rule codes if salaried structure has fewer rules than hourly after a clone pass
- ✅ Added `_register_hook` server-startup self-check: compares Hourly vs Salaried rule counts on every Odoo restart and logs ERROR if they differ
- ✅ `_post_init_hook` now also calls `_l10n_ca_clone_rules_to_salaried` directly (idempotent) to guarantee the salaried structure is populated on fresh installs
- ✅ Added OHP spot-check regression tests for annual incomes $15k / $25k / $36k / $48k / $48.6k / $50k / $65k / $72k / $73.2k / $100k / $200k / $250k
- ✅ Added ON $2,500 biweekly regression test: OHP ≈ $23.08/period, Provincial + OHP ≈ $131.48 (PDOC: $131.46, within ±$0.10)
- ⚠️ **Action required on existing databases**: run `-u l10n_ca_hr_payroll_except_QC` to apply the corrected OHP rates and re-clone salaried rules if any were missing

### v1.4 (April 2026) — Accounting Integration
- ✅ Added `hr_payroll_account` and `l10n_ca` to module dependencies — confirming a payslip now generates a balanced `account.move` in the Salary Journal
- ✅ Created 17 Canadian payroll GL accounts (9 liability 2xxx, 8 expense 5xxx) on module install, one set per Canadian company (idempotent)
- ✅ Created default Salary Journal (code `SAL`, type `general`) per company
- ✅ Wired `account_debit` / `account_credit` onto 12 salary rules (GROSS, RRSP, UNION_DUES, CPP_EE, CPP2_EE, EI_EE, FED_TAX, PROV_TAX, OHP, CPP_ER, CPP2_ER, EI_ER)
- ✅ OHP (Ontario Health Premium) credits 2340 Provincial Tax Payable; EHT accounts (5440/2350) created for future employer EHT rule
- ✅ `_post_init_hook` handles multi-company installs and is fully idempotent on upgrade

### v1.3 (April 2026)
- ✅ Read provincial tax config (`PROV_TAX` rule) from `l10n_ca_prov_tax_config` rule parameter so CRA connector updates take effect without a module upgrade; embedded 2026 values serve as fallback
- ✅ Read Ontario Health Premium config (`OHP` rule) from new `l10n_ca_ohp_config` rule parameter with 2026 tiers as fallback

### v1.2 (April 2026)
- ✅ Ship both **Canadian Employee — Hourly** and **Canadian Employee — Salaried** structure types out of the box
- ✅ Idempotent rule-clone helper (`_l10n_ca_clone_rules_to_salaried`) ensures both structures stay in sync on upgrades
- ✅ Demo data includes one hourly and one salaried employee contract

### v1.1 (March 2026)
- ✅ Added dynamic province detection for all 12 provinces/territories
- ✅ Added RRSP and Union Dues pre-tax deductions
- ✅ Ontario Health Premium conditionally applied (Ontario only)
- ✅ Federal BPA phase-out for high earners
- ✅ Ontario surtax calculation
- ✅ Year-End Reporting

### v1.0 (January 2026)
- Initial release
- CPP/CPP2/EI employee & employer contributions
- Federal income tax (5 brackets)
- Ontario provincial income tax
- Basic salary inputs (OT, Bonus, Commission)
- Employee SIN, TD1, Province fields
- Payslip report template
