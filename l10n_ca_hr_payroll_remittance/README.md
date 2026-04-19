# l10n_ca_hr_payroll_remittance

**Canada Payroll Remittance Workflow — CRA PD7A, Provincial EHT, WCB, RRSP, Union Dues**

Part of the [MapleHorn Consulting](https://www.maplehornconsulting.com) Canadian Payroll suite for Odoo 19.

---

## What This Module Does

This module adds a complete Canadian payroll remittance workflow on top of
`l10n_ca_hr_payroll_except_QC`. It turns Odoo into an end-to-end compliance
system by:

- Tracking what is owed to CRA, provincial agencies, and third parties
- Auto-generating remittance records on the correct schedule (daily cron)
- Computing due dates per CRA remitter type (Quarterly / Regular / Threshold 1 & 2)
- Producing payment journal entries that clear liability accounts
- Reconciling PD7A payments against T4 totals for year-end verification
- Printing PD7A Remittance Vouchers (QWeb PDF)
- Exporting PD7A CSV files for CRA bulk upload

> **Quebec excluded** — for Rest-of-Canada employers only.

---

## Installation

1. Install `l10n_ca_hr_payroll_except_QC` first (or this module will install it automatically as a dependency).
2. Copy `l10n_ca_hr_payroll_remittance` to your Odoo addons path.
3. Update Apps list and install **Canada — Payroll Remittance**.
4. The `_post_init_hook` will:
   - Create a "Receiver General for Canada" CRA vendor partner.
   - Create a default `RemittanceConfig` for each Canadian company.

---

## Configuration

Go to **Payroll → Year-End Reporting → Remittance Configuration**:

| Field | Description |
|---|---|
| **Remitter Type** | CRA assignment: Quarterly / Regular / Threshold 1 / Threshold 2 |
| **CRA Business Number** | Format: `123456789RP0001` |
| **EHT Account Number** | ON/MB/NL Employer Health Tax account |
| **WCB Account / Province** | Workers Compensation account |
| **Default Bank Journal** | Used for payment wizard default |
| **CRA Partner** | Vendor record for Receiver General for Canada |
| **Auto-Create Remittances** | Enable/disable daily cron for this company |

---

## Workflow

```
Payslips (done)
    ↓
[Daily cron] → Draft Remittance (with lines auto-generated)
    ↓
[Review] → Confirm (creates draft journal entry)
    ↓
[Payment Wizard] → Paid (posts journal entry + creates account.payment)
```

---

## Dashboard

Navigate to **Payroll → Year-End Reporting → Remittances**:

- **List view**: All remittances, color-coded (red = overdue, green = paid)
- **Kanban view**: Grouped by type, with overdue badge
- **Overdue Remittances**: Filtered view of past-due records
- **T4 Reconciliation**: Call `get_t4_reconciliation()` to compare PD7A totals to T4 box sums

---

## Reports

- **PD7A Remittance Voucher** (PDF): Available from the remittance form → Print button
- **PD7A CSV Export**: Action button on PD7A remittance form

---

## Technical Notes

- **Models**: `l10n.ca.remittance.config`, `l10n.ca.remittance`, `l10n.ca.remittance.line`
- **Wizard**: `l10n.ca.remittance.payment.wizard`
- **Cron**: `ir_cron_l10n_ca_create_remittances` (daily)
- **Unique constraint**: `(company_id, remittance_type, period_start, period_end)`
- **Multi-company**: All models scoped by `company_id` with record rules
- **License**: OPL-1

---

## Dependencies

```python
'depends': [
    'l10n_ca_hr_payroll_except_QC',
    'account',
    'hr_payroll_account',
]
```

Requires accounts 2310/2320/2321/2330/2340/2350/2360/2370/2380 + SAL journal
(created by `l10n_ca_hr_payroll_except_QC`'s `_post_init_hook`).

---

## License

OPL-1 — © MapleHorn Consulting Inc.
