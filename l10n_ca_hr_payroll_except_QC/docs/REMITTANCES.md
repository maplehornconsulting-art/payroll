# Canadian Payroll Remittances

This document explains how the remittance workflow inside
`l10n_ca_hr_payroll_except_QC` works, how remitter types are determined, and
how to reconcile PD7A submissions against T4 Summary data.

---

## Overview — Canadian Payroll Remittance Landscape

Canadian employers are required to remit source deductions to the **Canada
Revenue Agency (CRA)** and (where applicable) to provincial agencies and
third-party organisations.

| Category | Payee | Primary Form |
|---|---|---|
| Federal source deductions (CPP, EI, income tax) | Receiver General for Canada | PD7A |
| Ontario Employer Health Tax | Ontario Ministry of Finance | ON — EHT Return |
| BC Employer Health Tax | BC Government | BC — EHT Return |
| Manitoba Health & Post-Secondary Education Tax | MB Finance | Not modelled |
| Workers' Compensation (WCB/WSIB) | Provincial WCB | WCB Account |
| RRSP contributions | RRSP plan administrator | n/a |
| Union dues | Union | Collective agreement schedule |
| Garnishments | Court / creditor | Court order |

> **Quebec exclusion:** This module covers all provinces and territories
> *except* Quebec. QPP, QPIP, HSF, CNESST, and RQ remittances are out of
> scope; Quebec employers should use Revenu Québec forms instead.

---

## CRA Remitter Type — How It Is Determined

Each year CRA assigns a remitter type based on your **Average Monthly
Withholding Amount (AMWA)** calculated from payroll deductions remitted
*two calendar years prior*.

| Remitter Type | AMWA (two years prior) | CRA Schedule |
|---|---|---|
| **Quarterly** | < $3,000 | 15th of the month after quarter-end |
| **Regular** | $3,000 – $24,999.99 | 15th of the month following the pay period |
| **Threshold 1 (Accelerated)** | $25,000 – $99,999.99 | 25th (1st–15th payroll) or 10th of next month (16th–EOM payroll) |
| **Threshold 2 (Accelerated)** | ≥ $100,000 | 3 business days after the pay date |

Set your remitter type in **Payroll → Year-End Reporting → Remittance
Configuration**.

---

## Step-by-Step Workflow

### 1. Payslip computation

The employee's payslip is computed using the Canadian salary rules.
Key deductions are:

| Code | Description | GL Credit |
|---|---|---|
| `FED_TAX` | Federal income tax | 2310 |
| `CPP_EE` | CPP employee contribution | 2320 |
| `CPP_ER` | CPP employer contribution | 2320 |
| `CPP2_EE` | CPP2 employee contribution | 2321 |
| `CPP2_ER` | CPP2 employer contribution | 2321 |
| `EI_EE` | EI employee premium | 2330 |
| `EI_ER` | EI employer contribution (1.4×) | 2330 |
| `PROV_TAX` | Provincial income tax | 2340 |
| `EHT` | Employer Health Tax | 2350 |
| `RRSP` | RRSP deduction | 2360 |
| `UNION_DUES` | Union dues | 2370 |

### 2. Liability accumulation

When a payslip is **confirmed**, Odoo's `hr_payroll_account` bridge posts a
balanced `account.move` (journal entry) to the SAL journal.  Liability
accounts (2310–2370) accumulate credits representing amounts owed.

### 3. Automatic remittance creation (daily cron)

The cron job `ir_cron_l10n_ca_create_remittances` runs daily.

For each company with `auto_create_remittances = True`:

1. Determines the current remittance period based on remitter type.
2. Creates a **draft** `l10n.ca.remittance` record for each type
   (`cra_pd7a`, `provincial_eht`, `rrsp`, `union_dues`) if one does not
   already exist for that period (idempotent — protected by SQL unique
   constraint).
3. Attaches `done` payslips whose `date_to` falls in the period.
4. Aggregates journal entry lines from the attached payslips by liability
   account to populate `l10n.ca.remittance.line` records.
5. Schedules a reminder activity 5 business days before the due date.

### 4. Review and confirm

Open **Payroll → Year-End Reporting → Remittances** and review the draft
remittance.  You can:

- Adjust attached payslips and regenerate lines using **Generate Lines**.
- Add manual notes in the **Notes** tab.
- Print the **PD7A Remittance Voucher** PDF.
- Click **Confirm** to lock lines and generate a draft journal entry that
  debits the liability accounts and credits the Net Pay Clearing account
  (2380).

### 5. Register payment

Click **Register Payment** to open the payment wizard.  Enter:

- **Payment Date** — date the funds leave your account.
- **Bank / Cash Journal** — the bank account journal.
- **Payment Reference** — CRA or bank reference number.

On confirmation:

1. An `account.payment` (outbound vendor payment to the Receiver General)
   is created and posted.
2. The remittance journal entry is posted, clearing the liability accounts.
3. The payment and the remittance move are reconciled on the clearing
   account (2380).
4. Remittance state transitions to **Paid**.

---

## Due-Date Computation

| Remittance Type | Remitter Type | Formula |
|---|---|---|
| `cra_pd7a` | `quarterly` | 15th of month after quarter-end (Apr 15 / Jul 15 / Oct 15 / Jan 15) |
| `cra_pd7a` | `regular` | 15th of month following `period_end` |
| `cra_pd7a` | `threshold_1` | 25th (1st–15th payroll) or 10th of next month (16th–EOM payroll) |
| `cra_pd7a` | `threshold_2` | `period_end` + 3 business days |
| `provincial_eht` | any | March 15 of year following `period_end.year` |
| `wcb` | any | Last day of month following quarter-end |
| `rrsp` | any | `period_end` + 30 days |
| `union_dues` | any | 15th of month following `period_end` |
| `garnishment` | any | `period_end` + 7 days |

If the computed due date falls on a weekend, it is rolled forward to the
following Monday.  Canadian statutory holidays are not currently modelled;
verify manually if a due date falls near a federal holiday.

---

## Annual T4 ↔ PD7A Reconciliation

CRA cross-checks your **T4 Summary (Box 82)** total against the sum of all
PD7A remittances for the year.  A discrepancy can result in penalties.

The reconciliation widget is available via the model method
`get_t4_reconciliation(year=<int>)` and shows:

| Field | Source |
|---|---|
| `remittance_total` | Sum of `total_amount` for `cra_pd7a` remittances in **Paid** state for the year |
| `t4_total` | Sum of (T4 Box 16 CPP + Box 18 EI + Box 22 Fed Tax) across all confirmed/sent T4s for the year |
| `delta` | `abs(remittance_total − t4_total)` |
| `match` | `True` if `delta ≤ $1.00` |

### Sample reconciliation

```
T4 Summary Box 82  =  $741.72   (4 employees × 1 payslip each)
PD7A April total   =  $741.72

Delta = $0.00  ✓  Green — no discrepancy
```

Common causes of a mismatch:
- Payslips confirmed after the remittance period closed (attach them to the
  correct period's remittance and re-generate lines).
- Manual adjustments to T4 boxes without corresponding payslip corrections.
- Timing differences between pay date and remittance period.

---

## Override Hooks for Custom Remittance Types

To add a custom remittance type:

1. Extend the `remittance_type` Selection field in `l10n.ca.remittance` (via
   an inherited model in a downstream module):

   ```python
   remittance_type = fields.Selection(
       selection_add=[('my_type', 'My Custom Remittance')],
       ondelete={'my_type': 'cascade'},
   )
   ```

2. Add the liability account codes to `REMITTANCE_ACCOUNT_CODES`:

   ```python
   REMITTANCE_ACCOUNT_CODES['my_type'] = ['2399']
   ```

3. Override `_calc_due_date` to handle the new type's due-date logic.

4. If the cron should auto-create records for your type, override
   `_create_pending_remittances` and call `_ensure_remittance`.

---

## Configuration Reference

| Field | Description |
|---|---|
| `remitter_type` | CRA remitter classification (quarterly / regular / threshold_1 / threshold_2) |
| `cra_business_number` | 15-character CRA BN (e.g. `123456789RP0001`) |
| `eht_account_number` | Ontario / MB / NL EHT account number |
| `wcb_account_number` | WCB account number |
| `wcb_province` | Province for WCB remittances |
| `default_bank_journal_id` | Default bank journal used by the payment wizard |
| `cra_partner_id` | Vendor partner for CRA payments (Receiver General) |
| `auto_create_remittances` | Enable/disable the daily cron for this company |
