# Accounting Integration — Canadian Payroll GL Reference

This document describes how `l10n_ca_hr_payroll_except_QC` integrates with
Odoo Accounting (`hr_payroll_account`) to generate balanced journal entries
when payslips are confirmed.

---

## Overview

Confirming a payslip creates a single `account.move` in the **Salary Journal**
(`SAL`, type `general`).  Every payslip line that has `account_debit` **and**
`account_credit` configured on its salary rule produces two move lines.
Lines without accounts (BASIC, NET) are informational and do not post.

The net effect is:

| GL account | Direction | Why |
|---|---|---|
| 5410 Salaries & Wages Expense | **Debit** | Gross pay recognized as expense |
| 2380 Net Pay Clearing | Credit | Amount owed to employee |
| 2380 Net Pay Clearing | **Debit** × N | Each deduction reduces clearing |
| 2310–2380 Liability payables | Credit × N | Amounts owed to CRA / province / plan |
| 5420 CPP ER Expense | **Debit** | Employer CPP recognized as expense |
| 5421 CPP2 ER Expense | **Debit** | Employer CPP2 recognized as expense |
| 5430 EI ER Expense | **Debit** | Employer EI recognized as expense |
| 2320 CPP Payable | Credit | EE + ER CPP owed to CRA |
| 2321 CPP2 Payable | Credit | EE + ER CPP2 owed to CRA |
| 2330 EI Payable | Credit | EE + ER EI owed to CRA |

When the bank payment for net pay is recorded, the 2380 clearing account is
debited to zero.  When the CRA remittance is sent, the 2310–2340 liability
accounts are debited to zero.

---

## CRA PD7A Reconciliation Workflow

```
Period end:
  Sum 2310 credit balance → Federal Income Tax withheld → PD7A Line 1
  Sum 2320 credit balance → CPP (EE + ER) owed to CRA  → PD7A Line 2
  Sum 2330 credit balance → EI (EE + ER) owed to CRA   → PD7A Line 3

Remittance day:
  Dr 2310 / Cr Bank  (federal income tax payment)
  Dr 2320 / Cr Bank  (CPP EE + ER payment)
  Dr 2330 / Cr Bank  (EI EE + ER payment)
  Dr 2340 / Cr Bank  (provincial income tax + OHP payment)

Net pay day:
  Dr 2380 / Cr Bank  (pay employees — clears the clearing account)
```

---

## Full Debit / Credit Mapping

| Rule Code | Rule Name | Debit Account | Credit Account |
|---|---|---|---|
| BASIC | Basic Salary | *(informational)* | *(informational)* |
| GROSS | Gross Salary | **5410** Salaries & Wages Expense | **2380** Net Pay Clearing |
| RRSP | RRSP Deduction | **2380** Net Pay Clearing | **2360** RRSP Contributions Payable |
| UNION_DUES | Union Dues | **2380** Net Pay Clearing | **2370** Union Dues Payable |
| CPP_EE | CPP Employee | **2380** Net Pay Clearing | **2320** CPP Payable |
| CPP2_EE | CPP2 Employee | **2380** Net Pay Clearing | **2321** CPP2 Payable |
| EI_EE | EI Employee | **2380** Net Pay Clearing | **2330** EI Payable |
| FED_TAX | Federal Income Tax | **2380** Net Pay Clearing | **2310** Fed Tax Payable |
| PROV_TAX | Provincial Income Tax | **2380** Net Pay Clearing | **2340** Prov Tax Payable |
| OHP | Ontario Health Premium | **2380** Net Pay Clearing | **2340** Prov Tax Payable |
| NET | Net Salary | *(informational)* | *(informational)* |
| CPP_ER | CPP Employer | **5420** CPP ER Expense | **2320** CPP Payable |
| CPP2_ER | CPP2 Employer | **5421** CPP2 ER Expense | **2321** CPP2 Payable |
| EI_ER | EI Employer | **5430** EI ER Expense | **2330** EI Payable |
| *(future)* | EHT Employer | **5440** Ontario EHT Expense | **2350** Ontario EHT Payable |

> **Note on deduction rules (RRSP, UNION_DUES, CPP_EE, CPP2_EE, EI_EE, FED_TAX,
> PROV_TAX, OHP):** The table above shows the **effective** posting direction in
> the journal entry.  Because these rules return a *negative* result, Odoo's
> `hr_payroll_account` bridge swaps the `account_debit`/`account_credit` XML
> fields at posting time.  Therefore the XML field assignment is the *opposite*
> of what this table shows — the liability account is in `account_debit` and
> 2380 is in `account_credit`.  See [Gotcha section](#gotcha-negative-result--account_debitaccount_credit-semantics) below.

> **Note on OHP:** The Ontario Health Premium is an employee-side deduction
> remitted to the Ontario Ministry of Finance alongside provincial income tax.
> It therefore credits **2340 Provincial Tax Payable** (not 2350 which is
> reserved for the employer-side Employer Health Tax).

> **Note on EHT:** Accounts **5440** and **2350** are created on install for
> future use.  An EHT employer salary rule is not included in this module
> because Ontario Employer Health Tax is assessed on total annual payroll, not
> on individual payslips.  Employers subject to EHT can add a custom rule
> referencing these accounts.

---

## Accounts Created on Install

The following accounts are created idempotently (one set per Canadian company)
on module install or upgrade.

### Liability Accounts

| Code | Name |
|---|---|
| 2310 | CRA Source Deductions Payable — Federal Income Tax |
| 2320 | CRA Source Deductions Payable — CPP |
| 2321 | CRA Source Deductions Payable — CPP2 |
| 2330 | CRA Source Deductions Payable — EI |
| 2340 | Provincial Income Tax Withheld Payable |
| 2350 | Ontario EHT Payable *(future EHT rule)* |
| 2360 | RRSP Contributions Payable |
| 2370 | Union Dues Payable |
| 2380 | Net Pay Clearing |

### Expense Accounts

| Code | Name |
|---|---|
| 5410 | Salaries & Wages Expense |
| 5411 | Paid Time Off Expense *(future granular tracking)* |
| 5412 | Sick Time Off Expense *(future granular tracking)* |
| 5413 | Overtime Expense *(future granular tracking)* |
| 5420 | CPP Employer Contribution Expense |
| 5421 | CPP2 Employer Contribution Expense |
| 5430 | EI Employer Premium Expense |
| 5440 | Ontario EHT Expense *(future EHT rule)* |

---

## Worked Example: Weekly NS Payslip — $1,203.13 Gross

Assume a Nova Scotia employee, bi-weekly pay, $1,203.13 gross period earnings.
Approximate deductions (2026 rates):

| Rule | Amount | Debit | Credit |
|---|---|---|---|
| GROSS | +1,203.13 | 5410: 1,203.13 | 2380: 1,203.13 |
| CPP_EE | −56.49 | 2380: 56.49 | 2320: 56.49 |
| EI_EE | −19.61 | 2380: 19.61 | 2330: 19.61 |
| FED_TAX | −180.00 | 2380: 180.00 | 2310: 180.00 |
| PROV_TAX | −120.00 | 2380: 120.00 | 2340: 120.00 |
| OHP | −0.00 | *(NS — OHP not applied)* | |
| NET | +827.03 | *(informational)* | |
| CPP_ER | +56.49 | 5420: 56.49 | 2320: 56.49 |
| CPP2_ER | +0.00 | *(nil)* | |
| EI_ER | +27.45 | 5430: 27.45 | 2330: 27.45 |

**Journal entry summary (all values approximate):**

```
Dr  5410  Salaries & Wages Expense     1,203.13
Dr  5420  CPP ER Expense                  56.49
Dr  5430  EI ER Expense                   27.45
    Cr  2310  Fed Tax Payable            180.00
    Cr  2320  CPP Payable (EE+ER)        112.98
    Cr  2330  EI Payable (EE+ER)          47.06
    Cr  2340  Prov Tax Payable           120.00
    Cr  2380  Net Pay Clearing           827.03
                                      ─────────
Total debits   = 1,287.07
Total credits  = 1,287.07  ✓
```

> Actual amounts will vary based on annualized income, CPP/EI year-to-date
> maximums, and the employee's TD1 claim code.

---

## CPP / CPP2 Annual Cap Behaviour

### CRA rule

The Canada Revenue Agency mandates an **annual** (not per-period) maximum
employee CPP contribution.  The rule for every pay period is:

```
remaining_annual = max(annual_max − ytd_cpp, 0)
period_deduction = min(period_contribution, remaining_annual)
```

where `ytd_cpp` is the sum of confirmed CPP deductions for this employee in
the current calendar year, across all payslips with state `done` or `paid`
whose `date_to` is before the current payslip's `date_from`.

### Why this matters

High earners legitimately hit the annual maximum early in the year and then
make **zero** further CPP contributions for the remainder of the year.  An
Ontario employee earning $9,625/week (≈ $500K/year) should contribute
≈ $568.68 on the first payslip (exhausting most of the annual budget) — not
the per-period smeared amount of ≈ $81.35 (`annual_max ÷ 52`).

Using a per-period cap causes:
- **Permanent under-deduction** for high earners (each period caps too low).
- **T4 Box 16 / 16A understated**, which the employee may need to true-up via
  their personal tax return.
- **Under-remittance to CRA** on the PD7A, exposing the employer to CRA
  reassessment plus the 10% penalty under ITA s. 227(9).

The same annual-cap logic applies to CPP2 and to the EI annual premium ceiling.

### Implementation — `_l10n_ca_ytd_amount`

The helper `HrPayslip._l10n_ca_ytd_amount(code)` in
`models/hr_payslip.py` performs an ORM search for prior payslip lines:

- Same `employee_id`
- Same calendar year as `self.date_from`
- Payslip state `in ('done', 'paid')` — draft/cancelled payslips are excluded
- `slip_id.date_to < self.date_from` — only payslips that ended before
  the current payslip starts
- `salary_rule_id.code == code`

It returns `sum(abs(line.total) for line in lines)`.

Both the salary rule XML (`data/hr_salary_rule_data.xml`) and the Python model
helper (`_l10n_ca_get_payslip_line_values`) call this method to enforce the
same cap logic.

### Prior-system YTD import (migration caveat)

If you are migrating from another payroll system **mid-year**, the module has
no knowledge of contributions already made under the prior system.  Without
YTD seeding, the first Odoo payslip for each employee will see `ytd = 0`
and may over-deduct CPP/CPP2/EI relative to the true remaining annual headroom.

**Recommended approach:**

1. For each employee, calculate year-to-date CPP, CPP2, EI, FIT, and PIT
   contributions made under the prior system up to (but not including) the
   first Odoo payslip start date.
2. Create a *synthetic* payslip per employee in Odoo:
   - Set `date_from` / `date_to` to any period within the same calendar year
     that ends before the first real payslip's `date_from`.
   - Manually enter line amounts matching the prior-system YTD totals for
     CPP_EE, CPP2_EE, EI_EE (and optionally FED_TAX, PROV_TAX).
   - Confirm/lock the payslip (`state = 'done'`).
3. From the first real payslip onward, `_l10n_ca_ytd_amount` will pick up the
   synthetic YTD payslip and apply the correct remaining headroom.

> **Warning:** If you skip this step, the first real payslips after migration
> will deduct the full remaining annual headroom (potentially a large amount).
> Always reconcile CPP/EI YTD before processing the first payroll run in Odoo.

---

## K2 / K2P Non-Refundable Tax Credit Projection

### CRA T4127 reference

The CRA Payroll Deductions Formulas (T4127) define **K2** (federal) and **K2P**
(provincial) non-refundable credits for the employee's CPP, CPP2, and EI
contributions, applied at the lowest marginal rate in each jurisdiction:

```
K2  = (annual_CPP + annual_CPP2 + annual_EI) × lowest_federal_rate
K2P = (annual_CPP + annual_CPP2 + annual_EI) × lowest_provincial_rate
```

These credits reduce the employee's income-tax source-deduction each period.

### Why naive annualization breaks for high earners

A naïve implementation multiplies the **current-period** contribution by the
number of periods per year:

```python
annual_cpp = abs(CPP_EE_this_period) * periods   # ← BUG for high earners
```

This is correct only when the employee contributes the same amount every period.
For a **high earner** (e.g. Ontario weekly, $9,625/wk ≈ $500 K/yr) who hits the
annual CPP cap around week 8:

| Week | CPP_EE | Naïve K2 base | Effect |
|------|--------|---------------|--------|
| 1–7  | $568.68 | $568.68 × 52 ≈ $29,571 → capped → $4,230 ✓ | correct |
| 8    | ~$250   | $250 × 52 = $13,000 → capped → $4,230 ✓ | correct |
| 9–52 | **$0**  | **$0 × 52 = $0 → K2 = $0** | ❌ credit lost → tax over-withheld |

Weeks 9–52 the employee is **over-withheld** for the remainder of the year
because the entire CPP non-refundable credit disappears once CPP_EE = $0.

### Fix — `_l10n_ca_projected_annual_contribution`

The helper `HrPayslip._l10n_ca_projected_annual_contribution(code, period_amount, annual_max)`
computes a **YTD-aware projected annual contribution**:

```
ytd        = _l10n_ca_ytd_amount(code)       # prior done/paid payslips
current    = abs(period_amount)              # this period
remaining  = max(periods − periods_elapsed − 1, 0)
projected  = ytd + current + remaining × current
return min(projected, annual_max)
```

For week 9 (ytd = $4,230, current = $0, remaining = 43):

```
projected = 4,230 + 0 + 43 × 0 = 4,230 → min(4,230, 4,230) = $4,230 ✓
```

The credit is preserved at the full annual value even after the cap is consumed.

For week 1 of any high earner (ytd = $0, current = $568.68, remaining = 51):

```
projected = 0 + 568.68 + 51 × 568.68 = 29,571 → capped at $4,230 ✓
```

For a low earner who never caps (ytd = 0, current = $67.59, remaining = 51):

```
projected = 0 + 67.59 + 51 × 67.59 = 3,514 < $4,230 → $3,514 (same as naive) ✓
```

Low and mid earners are unaffected — their tax is identical to the old formula.

### Implementation

| Helper | Used by |
|--------|---------|
| `_l10n_ca_ytd_amount(code)` | CPP_EE, CPP2_EE, EI_EE rules (annual cap enforcement) |
| `_l10n_ca_projected_annual_contribution(code, period_amount, annual_max)` | FED_TAX (K2), PROV_TAX (K2P) — annual credit projection |

Both helpers are defined on `hr.payslip` in `models/hr_payslip.py`.

The `_l10n_ca_projected_annual_contribution` helper calls `_l10n_ca_ytd_amount`
internally and also counts prior done/paid payslips via `hr.payslip.search_count`
to determine `periods_elapsed`.

---

1. **Go to** Payroll → Configuration → Salary Rules
2. **Filter** by structure "Canadian Employee — Hourly" (or Salaried)
3. **Open** the rule (e.g. "Federal Income Tax")
4. **Change** the Debit Account and/or Credit Account fields to your
   company-specific accounts
5. Repeat for any other rules that need different accounts

> Overrides are stored per salary rule record and are not reset by module
> upgrades (the rules use `noupdate="0"` but only new rules are added; existing
> rule account assignments are not reverted unless you reinstall the module).

---

## Multi-Company Notes

- On module install, the `_post_init_hook` creates accounts and the SAL journal
  for every `res.company` where `country_id.code == 'CA'`.
- The SAL journal is also assigned to the Canadian payroll structures when
  `hr_payroll_account` is installed.
- If you add a new Canadian company after the module is already installed, run
  the `_post_init_hook` manually from a Odoo shell or reinstall the module.

---

## Quebec Exclusion

This module is named `_except_QC` by design.  No QPP, QPIP, HSF, CNESST, or
Revenu Québec accounts are created.  For Quebec employees, use a separate
`l10n_ca_qc_hr_payroll` module (not included).

---

## Gotcha: Negative result + account_debit/account_credit semantics

### How Odoo posts salary rules to journal entries

Odoo's `hr_payroll_account` bridge applies the following rule when converting
a payslip line into `account.move.line` entries:

| `salary_line.total` | Debit side | Credit side |
|---|---|---|
| **positive** (`> 0`) | `rule.account_debit` | `rule.account_credit` |
| **negative** (`< 0`) | `rule.account_credit` | `rule.account_debit` (abs value) |

In other words, **when the formula result is negative, Odoo swaps the two
account fields**.

### Why this matters for employee deductions

Employee deduction rules (CPP_EE, EI_EE, FED_TAX, PROV_TAX, OHP, RRSP,
UNION_DUES) all use a negative formula result — for example:

```python
result = -min(pensionable * cpp_rate, period_max)   # always ≤ 0
```

To achieve the desired journal entry `Dr 2380 Net Pay Clearing / Cr 2320 CPP Payable`,
the accounts must be assigned **counter-intuitively**:

| XML field | Account set | Why |
|---|---|---|
| `account_debit` | **2320** CPP Payable (liability) | Odoo will *credit* this when result < 0 |
| `account_credit` | **2380** Net Pay Clearing | Odoo will *debit* this when result < 0 |

The `<!-- Dr 2380 Net Pay Clearing / Cr 2320 CPP Payable -->` comment above each
rule in `hr_salary_rule_data.xml` describes the **effective journal entry direction**
(i.e., what you will see in the posted `account.move`), **not** the literal field
assignment.

### Worked example — CPP_EE, $5 000 bi-weekly, Ontario 2026

1. `CPP_EE.result = -139.28`  (negative — employee CPP contribution)
2. Odoo sees `total < 0` → uses `account_credit` for debit, `account_debit` for credit
3. XML has: `account_debit = account_2320`, `account_credit = account_2380`
4. Posted move lines:
   ```
   Dr  2380  Net Pay Clearing    139.28   ← from account_credit field
   Cr  2320  CPP Payable         139.28   ← from account_debit field
   ```
5. **Net effect:** Net Pay Clearing is reduced (the cleared amount will be paid
   to CRA rather than the employee), and CPP Payable grows by $139.28.

### Employer-side rules are NOT affected

Employer rules (CPP_ER, CPP2_ER, EI_ER) use a **positive** result
(e.g., `result = -cpp_ee_total` where `cpp_ee_total` is already negative, so
the double negative gives a positive value).  Odoo does **not** swap accounts
for positive results, so the field assignment for employer rules is
straightforward: `account_debit = 5420` (expense), `account_credit = 2320`
(payable).

### Canonical check

The integration test `tests/test_journal_posting_directions.py` verifies the
effective posting direction end-to-end.  Run it inside a live Odoo instance
with this module installed:

```bash
odoo-bin -c odoo.conf -d mydb --test-enable \
  --test-tags /l10n_ca_hr_payroll_except_QC:l10n_ca_payroll_accounting
```

If CPP Payable (2320) ever shows a **debit** entry from a payslip confirmation,
the `account_debit`/`account_credit` fields on the deduction rule have been
swapped back to the buggy state.

