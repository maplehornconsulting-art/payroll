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

## Overriding Account Mapping Per Company

To use different GL accounts for a company:

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
