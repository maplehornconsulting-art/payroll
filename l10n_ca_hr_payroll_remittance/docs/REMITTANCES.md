# Canadian Payroll Remittance — Module Documentation

## Overview

`l10n_ca_hr_payroll_remittance` extends the `l10n_ca_hr_payroll_except_QC` module
to provide a **complete Canadian payroll remittance workflow** for employers in
all provinces and territories except Quebec.

---

## The Canadian Payroll Remittance Landscape

### Who You Remit To

| Type | Agency | Key Form |
|---|---|---|
| Federal source deductions (CPP + EI + Fed Tax) | Canada Revenue Agency (CRA) | PD7A |
| Provincial income tax withheld | CRA (via PD7A) | PD7A |
| Ontario / Manitoba / NL Employer Health Tax | Provincial Ministry of Finance | ON EHT Return |
| Workers' Compensation | Provincial WCB/WSIB | WCB/WSIB return |
| RRSP contributions | Plan administrator | Per plan terms |
| Union dues | Union | Per CBA |
| Garnishments | Court / enforcement body | Court order |

### PD7A — The Core Federal Remittance

The **PD7A Statement of Account for Current Source Deductions** is the primary
CRA remittance form. It covers:
- Federal income tax withheld
- CPP employee + employer contributions
- CPP2 employee + employer contributions (for earnings above Year's Maximum Pensionable Earnings)
- EI employee premiums + employer premiums (× 1.4 or lower insured rate)

---

## Remitter Types and Schedules

CRA assigns your remitter type annually based on your **Average Monthly Withholding
Amount (AMWA)** from two calendar years prior.

| Type | AMWA | Remittance Due Date |
|---|---|---|
| **Quarterly** | < $3,000 | 15th of month after quarter-end (Apr 15, Jul 15, Oct 15, Jan 15) |
| **Regular** | $3,000 – $24,999.99 | 15th of month following payroll period |
| **Threshold 1 Accelerated** | $25,000 – $99,999.99 | 25th (payrolls 1–15 of month); 10th of next month (payrolls 16–EOM) |
| **Threshold 2 Accelerated** | ≥ $100,000 | 3 business days after each payroll |

New employers default to **Regular** until CRA establishes their AMWA.

---

## Step-by-Step: Payslip → Remittance → Payment

### 1. Payslip Confirmation

When a payslip is confirmed (`hr.payslip.action_payslip_done`), `hr_payroll_account`
posts a balanced `account.move`:

```
Dr  5410  Salaries & Wages Expense          ×  gross
Dr  5420  CPP Employer Contribution Expense ×  cpp_er
Dr  5430  EI Employer Premium Expense       ×  ei_er
Cr  2310  Federal Income Tax Payable        ×  fed_tax
Cr  2320  CPP Payable                       ×  cpp_ee + cpp_er
Cr  2330  EI Payable                        ×  ei_ee + ei_er
Cr  2340  Provincial Tax Payable            ×  prov_tax
Cr  2380  Net Pay Clearing                  ×  net_pay
```

Liability accounts 2310 / 2320 / 2321 / 2330 accumulate **credits** throughout
the pay period.

### 2. Automatic Remittance Creation (Daily Cron)

The `ir_cron_l10n_ca_create_remittances` cron runs daily and, for each company
with `auto_create_remittances = True`:

1. Determines the current period boundaries from `remitter_type`.
2. Calls `l10n.ca.remittance._ensure_remittance()` for each type
   (`cra_pd7a`, `provincial_eht`, `rrsp`, `union_dues`).
3. Attaches all `done` payslips whose `date_to` falls in the period.
4. Generates `l10n.ca.remittance.line` records by querying account balances.
5. Schedules a `mail.activity` for the payroll manager 5 business days before
   each `due_date`.

### 3. Review and Confirm

Open **Payroll → Year-End Reporting → Remittances**. Review the draft remittance:

- Verify lines match expected liabilities.
- Add or remove payslips if needed.
- Click **Generate Lines** to recalculate.
- Click **Confirm** (validates `total_amount > 0`, creates a draft journal entry).

### 4. Register Payment

Click **Register Payment**. In the wizard:

- Set `Payment Date`, `Bank Journal`, and `Payment Reference`.
- Click **Confirm Payment**:
  - Creates an `account.payment` (vendor payment to CRA partner).
  - Posts the remittance journal entry (clears liability accounts).
  - Attempts reconciliation of clearing lines.
  - Sets state = `paid`.

### 5. Print Voucher

From a confirmed or paid remittance, click **Print Voucher** to generate the
**PD7A Remittance Voucher** PDF, which includes:
- Business number, period dates, due date
- Itemized breakdown (Fed Tax, CPP, EI)
- Total
- Payment instructions

---

## Annual T4/PD7A Reconciliation

CRA cross-checks **T4 Summary Box 82** (total source deductions) against the
sum of your PD7A remittances for the year. They should match (within rounding).

### Widget Logic

In Odoo, call `l10n.ca.remittance.get_t4_reconciliation(year=YYYY)` to get:

```python
{
    'match': True,          # True if delta <= $1.00
    'delta': 0.00,
    'remittance_total': 741.72,  # Sum of paid cra_pd7a for the year
    't4_total': 741.72,          # Sum of T4 box 16+18+22 for all employees
    'year': 2026,
}
```

**Green ✓** if `match = True`, **Red ✗ with delta** if not.

### Sample Reconciliation

| | Amount |
|---|---|
| Total PD7A paid (2026) | $8,900.64 |
| T4 Summary Box 82 (box 16+18+22 totals) | $8,900.64 |
| **Match** | ✓ |

If there is a discrepancy, check for:
- Payslips in `done` state not linked to a remittance.
- Manual journal entries that bypassed payslips.
- T4s not yet computed (still in `draft` state).
- Payslips with `date_to` outside the period.

---

## Override Hooks for Custom Remittance Types

### Adding a Custom Type

1. Override `remittance_type` selection field in your custom module:

```python
from odoo import fields, models

class L10nCaRemittance(models.Model):
    _inherit = 'l10n.ca.remittance'

    remittance_type = fields.Selection(
        selection_add=[('my_custom_type', 'My Custom Remittance')],
        ondelete={'my_custom_type': 'cascade'},
    )
```

2. Override `_calc_due_date()` to handle your new type.

3. Update `REMITTANCE_ACCOUNT_CODES` if your type aggregates specific accounts.

### Custom WCB Schedules

WCB schedules vary by province (monthly in BC, quarterly in AB, etc.).
Override `_current_period_bounds()` to return the appropriate period for your
WCB province.

---

## Quebec Exclusion

This module is intentionally **Quebec-free**. Quebec employers must remit to
Revenu Québec for QPP, QPIP, HSF, and CNESST — which have different forms,
schedules, and online portals. A separate `l10n_ca_qc_hr_payroll_remittance`
module would be needed for Quebec employers.

---

## Multi-Company Support

Every model has a `company_id` field. Record rules scope all reads/writes to the
current user's `company_ids`. The daily cron iterates over all companies with
`auto_create_remittances = True`.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Lines not generated | Payslips not attached, or moves not posted | Attach payslips, check `move_id.state == 'posted'` |
| "Account 2380 not found" on Confirm | GL accounts not set up | Run `_post_init_hook` or reinstall `l10n_ca_hr_payroll_except_QC` |
| Reconciliation fails | Clearing account not `reconcile=True` | Set `reconcile = True` on account 2380 |
| T4 reconciliation shows mismatch | T4s in draft state | Confirm all T4s |
