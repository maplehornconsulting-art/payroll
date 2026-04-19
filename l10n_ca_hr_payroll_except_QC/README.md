# Canada Payroll — All Provinces & Territories (Except Quebec)

## Compatibility

| | |
|---|---|
| **Odoo Edition** | Enterprise (required) |
| **Minimum Version** | 18.0 |
| **Python** | 3.10+ |
| **Dependencies** | `hr_payroll`, `hr_work_entry_holidays`, `hr_payroll_holidays` |

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
- **Federal Income Tax** — 5-bracket progressive tax with Basic Personal Amount (BPA) phase-out for high earners
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
- Federal BPA phase-out between Bracket 3 and Bracket 4 for high earners
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

## Compatibility

| | Version |
|---|---|
| **Odoo Edition** | Enterprise |
| **Odoo Version** | 18.0 |
| **Python** | 3.10+ |
| **Dependencies** | `hr_payroll`, `hr_work_entry_holidays`, `hr_payroll_holidays` |

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
