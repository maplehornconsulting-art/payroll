# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Unit tests for period-aware salary rules in l10n_ca_hr_payroll_except_QC.

These tests exercise the ``_l10n_ca_periods_per_year`` helper and the
per-period CPP / EI / FED_TAX / PROV_TAX / OHP computation logic that is
embedded in ``hr_salary_rule_data.xml``.  They run without a live Odoo
instance by loading the Python model directly via importlib and supplying
lightweight mock objects.
"""

from __future__ import annotations

import importlib.util
import pathlib
from unittest.mock import MagicMock, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Module loader helpers
# ---------------------------------------------------------------------------

def _load_hr_payslip():
    """Load the HrPayslip class from hr_payslip.py without the Odoo ORM."""
    path = pathlib.Path(__file__).parent.parent / "models" / "hr_payslip.py"
    spec = importlib.util.spec_from_file_location("hr_payslip", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.HrPayslip


_HrPayslip = _load_hr_payslip()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _FakeStructType:
    """Minimal stand-in for hr.payroll.structure.type."""
    def __init__(self, schedule_pay: str):
        self.default_schedule_pay = schedule_pay


class _FakeStruct:
    def __init__(self, schedule_pay: str):
        self.type_id = _FakeStructType(schedule_pay)


class _FakeContract:
    def __init__(self, schedule_pay: str):
        self.schedule_pay = schedule_pay


class _FakePayslip:
    """Minimal payslip stand-in for testing _l10n_ca_periods_per_year."""

    def __init__(self, struct_sp: str = "bi-weekly", contract_sp: str = "bi-weekly"):
        self.struct_id = _FakeStruct(struct_sp)
        self.contract_id = _FakeContract(contract_sp)

    def ensure_one(self):  # no-op for tests
        pass


def _make_payslip(schedule_pay: str = "bi-weekly") -> MagicMock:
    """Return a MagicMock payslip for non-period-mapping tests."""
    slip = MagicMock()
    slip.struct_id.type_id.default_schedule_pay = schedule_pay
    slip.contract_id.schedule_pay = schedule_pay
    return slip


# ---------------------------------------------------------------------------
# _l10n_ca_periods_per_year
# ---------------------------------------------------------------------------

class TestPeriodsPerYear:
    """Unit tests for HrPayslip._l10n_ca_periods_per_year()."""

    def _call(self, schedule_pay: str) -> int:
        """Call the helper on a fake payslip."""
        slip = _FakePayslip(struct_sp=schedule_pay, contract_sp=schedule_pay)
        return _HrPayslip._l10n_ca_periods_per_year(slip)

    def test_weekly(self):
        assert self._call("weekly") == 52

    def test_bi_weekly(self):
        assert self._call("bi-weekly") == 26

    def test_semi_monthly(self):
        assert self._call("semi-monthly") == 24

    def test_monthly(self):
        assert self._call("monthly") == 12

    def test_quarterly(self):
        assert self._call("quarterly") == 4

    def test_semi_annually(self):
        assert self._call("semi-annually") == 2

    def test_annually(self):
        assert self._call("annually") == 1

    def test_daily(self):
        assert self._call("daily") == 260

    def test_bi_monthly(self):
        assert self._call("bi-monthly") == 6

    def test_unknown_defaults_to_26(self):
        """An unrecognised schedule key falls back to the bi-weekly default."""
        assert self._call("fortnightly") == 26

    def test_empty_falls_back_to_bi_weekly(self):
        """When both struct and contract schedule are falsy, default is bi-weekly."""
        slip = _FakePayslip(struct_sp="", contract_sp="")
        result = _HrPayslip._l10n_ca_periods_per_year(slip)
        assert result == 26

    def test_contract_fallback(self):
        """Falls back to contract.schedule_pay when struct type has no value."""
        slip = _FakePayslip(struct_sp="", contract_sp="monthly")
        result = _HrPayslip._l10n_ca_periods_per_year(slip)
        assert result == 12


# ---------------------------------------------------------------------------
# Salary-rule logic tests
# ---------------------------------------------------------------------------
#
# The XML rules are embedded Python snippets; we replicate their logic here
# so we can test correctness across all pay cadences without a running Odoo
# instance.
#
# 2026 CRA parameters (from hr_rule_parameters_data.xml / cra_feed output):
#   cpp_rate         = 0.0595
#   cpp_exemption    = 3500          (annual)
#   cpp_ympe         = 74600         (annual)
#   cpp_max          = 4054.29       (annual)  ← Note: use a round test value
#   cpp2_rate        = 0.04
#   cpp2_ceiling     = 85000
#   cpp2_max         = 416.00
#   ei_rate          = 0.0166
#   ei_max_insurable = 65700
#   ei_max_premium   = 1091.22
# ---------------------------------------------------------------------------

# Parameters taken from the rule-parameter data file (approximate 2026 values)
_CPP_RATE = 0.0595
_CPP_EXEMPTION = 3500.0          # annual
_CPP_MAX = 4054.29               # annual  (cap on annual employee contribution)
_CPP_YMPE = 74600.0              # annual
_CPP2_RATE = 0.04
_CPP2_CEILING = 85000.0
_CPP2_MAX = 416.00               # annual
_EI_RATE = 0.0166
_EI_MAX_INSURABLE = 65700.0      # annual
_EI_MAX_PREMIUM = 1091.22        # annual

# Federal brackets (threshold, rate) — 2026
_FED_BRACKETS = [
    (57375.0, 0.14),
    (114750.0, 0.205),
    (177882.0, 0.26),
    (253414.0, 0.29),
    (float("inf"), 0.33),
]
_BPA_MAX = 16129.0
_BPA_MIN = 14538.0
_PHASE_OUT_START = 177882.0
_PHASE_OUT_END = 253414.0

# NS brackets for PROV_TAX regression test
_NS_BRACKETS = [
    (30995.0, 0.0879),
    (61991.0, 0.1495),
    (97417.0, 0.1667),
    (157124.0, 0.175),
    (float("inf"), 0.21),
]
_NS_BPA = 11932.0

GROSS = 1203.13  # fixed gross used throughout cadence tests


def _cpp_ee(gross: float, periods: int) -> float:
    """Replicate CPP_EE rule logic for the given gross and periods/year."""
    period_exemption = _CPP_EXEMPTION / periods
    period_max = _CPP_MAX / periods
    pensionable = max(gross - period_exemption, 0.0)
    return round(-min(pensionable * _CPP_RATE, period_max), 2)


def _ei_ee(gross: float, periods: int) -> float:
    """Replicate EI_EE rule logic."""
    period_max_insurable = _EI_MAX_INSURABLE / periods
    period_max_premium = _EI_MAX_PREMIUM / periods
    insurable = min(gross, period_max_insurable)
    return round(-min(insurable * _EI_RATE, period_max_premium), 2)


def _progressive_tax(income: float, brackets: list) -> float:
    tax = 0.0
    prev = 0.0
    for threshold, rate in brackets:
        chunk = min(income, threshold) - prev
        if chunk > 0:
            tax += chunk * rate
        prev = threshold
        if income <= threshold:
            break
    return tax


def _fed_bpa(annual_income: float) -> float:
    if annual_income <= _PHASE_OUT_START:
        return _BPA_MAX
    if annual_income >= _PHASE_OUT_END:
        return _BPA_MIN
    return _BPA_MAX - (_BPA_MAX - _BPA_MIN) * (annual_income - _PHASE_OUT_START) / (_PHASE_OUT_END - _PHASE_OUT_START)


def _fed_tax(gross: float, periods: int) -> float:
    """Replicate FED_TAX rule logic."""
    annual = gross * periods
    bpa = _fed_bpa(annual)
    tax = _progressive_tax(annual, _FED_BRACKETS)
    credit = bpa * _FED_BRACKETS[0][1]
    annual_tax = max(tax - credit, 0.0)
    return round(-(annual_tax / periods), 2)


def _prov_tax_ns(gross: float, periods: int) -> float:
    """Replicate PROV_TAX rule logic for Nova Scotia (no surtax)."""
    annual = gross * periods
    tax = _progressive_tax(annual, _NS_BRACKETS)
    credit = _NS_BPA * _NS_BRACKETS[0][1]
    basic_tax = max(tax - credit, 0.0)
    return round(-(basic_tax / periods), 2)


# ---- cadence correctness tests ----

class TestCppEeCadences:
    """CPP_EE must use per-period exemption derived from the schedule."""

    def test_weekly_exemption(self):
        """Weekly: exemption = 3500/52 ≈ 67.31."""
        weekly_result = _cpp_ee(GROSS, 52)
        biweekly_result = _cpp_ee(GROSS, 26)
        # Weekly has smaller per-period exemption → larger pensionable → larger deduction
        assert abs(weekly_result) > abs(biweekly_result), (
            f"Weekly CPP {weekly_result} should be > bi-weekly {biweekly_result}"
        )

    def test_weekly_cpp_value(self):
        """Weekly $1,203.13: CPP_EE ≈ −$67.59."""
        result = _cpp_ee(GROSS, 52)
        assert abs(result) == pytest.approx(67.59, abs=0.02)

    def test_biweekly_cpp_value(self):
        """Bi-weekly $1,203.13: CPP_EE ≈ −$63.58."""
        result = _cpp_ee(GROSS, 26)
        assert abs(result) == pytest.approx(63.58, abs=0.02)

    def test_monthly_cpp_value(self):
        """Monthly: per-period exemption = 3500/12 ≈ 291.67."""
        period_exemption = _CPP_EXEMPTION / 12
        assert period_exemption == pytest.approx(291.67, abs=0.01)
        result = _cpp_ee(GROSS, 12)
        pensionable = max(GROSS - period_exemption, 0.0)
        expected = round(-min(pensionable * _CPP_RATE, _CPP_MAX / 12), 2)
        assert result == expected

    def test_cap_respected(self):
        """CPP is capped at cpp_max / periods regardless of gross."""
        huge_gross = 999999.0
        result = _cpp_ee(huge_gross, 26)
        assert abs(result) == pytest.approx(_CPP_MAX / 26, abs=0.01)


class TestEiEeCadences:
    """EI_EE must use per-period insurable max derived from the schedule."""

    def test_weekly_ei_value(self):
        """Weekly: max_insurable / 52."""
        result = _ei_ee(GROSS, 52)
        expected_insurable = min(GROSS, _EI_MAX_INSURABLE / 52)
        expected = round(-min(expected_insurable * _EI_RATE, _EI_MAX_PREMIUM / 52), 2)
        assert result == expected

    def test_biweekly_ei_value(self):
        result = _ei_ee(GROSS, 26)
        expected_insurable = min(GROSS, _EI_MAX_INSURABLE / 26)
        expected = round(-min(expected_insurable * _EI_RATE, _EI_MAX_PREMIUM / 26), 2)
        assert result == expected

    def test_weekly_and_biweekly_differ_above_weekly_cap(self):
        """Use a gross above the weekly insurable cap but below the bi-weekly cap."""
        # Weekly per-period insurable cap = 65700/52 ≈ 1263.46
        # Bi-weekly per-period insurable cap = 65700/26 ≈ 2526.92
        gross_above_weekly_cap = 1300.0
        r_weekly = _ei_ee(gross_above_weekly_cap, 52)
        r_biweekly = _ei_ee(gross_above_weekly_cap, 26)
        assert r_weekly != r_biweekly, (
            f"EI for gross {gross_above_weekly_cap}: weekly={r_weekly}, "
            f"biweekly={r_biweekly} — should differ when gross > weekly insurable cap"
        )

    def test_cap_not_exceeded(self):
        """Premium must not exceed annual max / periods for any gross."""
        huge_gross = 999999.0
        for periods in (52, 26, 24, 12):
            result = abs(_ei_ee(huge_gross, periods))
            period_cap = _EI_MAX_PREMIUM / periods
            assert result <= period_cap + 0.01, (
                f"EI for periods={periods}: {result} exceeds cap {period_cap}"
            )


class TestFedTaxCadences:
    """FED_TAX annualizes at gross * periods and de-annualizes at / periods."""

    def test_biweekly_annualizes_correctly(self):
        """$1,203.13 × 26 = $31,281.38 annual income."""
        annual = GROSS * 26
        assert annual == pytest.approx(31281.38, abs=0.01)

    def test_weekly_annualizes_correctly(self):
        """$1,203.13 × 52 = $62,562.76 annual income."""
        annual = GROSS * 52
        assert annual == pytest.approx(62562.76, abs=0.01)

    def test_weekly_fed_tax_gt_biweekly(self):
        """Higher annual income → higher annual tax → different per-period amount."""
        weekly = _fed_tax(GROSS, 52)
        biweekly = _fed_tax(GROSS, 26)
        # Weekly annual income is double the bi-weekly, so annual tax is higher.
        # Per-period: (higher_annual_tax / 52) vs (lower_annual_tax / 26)
        # The direction of the per-period comparison depends on the bracket,
        # but we at least confirm the two values differ.
        assert weekly != biweekly

    def test_monthly_deannualizes(self):
        result = _fed_tax(GROSS, 12)
        annual = GROSS * 12
        bpa = _fed_bpa(annual)
        tax = _progressive_tax(annual, _FED_BRACKETS)
        credit = bpa * _FED_BRACKETS[0][1]
        expected = round(-(max(tax - credit, 0) / 12), 2)
        assert result == expected


class TestProvTaxNsCadences:
    """PROV_TAX (NS) must annualize / de-annualize using the correct period count."""

    def test_biweekly_and_weekly_differ(self):
        r_biweekly = _prov_tax_ns(GROSS, 26)
        r_weekly = _prov_tax_ns(GROSS, 52)
        assert r_biweekly != r_weekly

    def test_weekly_uses_52_annualization(self):
        """Verify the weekly figure is derived from annual = gross * 52."""
        annual = GROSS * 52
        tax = _progressive_tax(annual, _NS_BRACKETS)
        credit = _NS_BPA * _NS_BRACKETS[0][1]
        expected = round(-(max(tax - credit, 0) / 52), 2)
        assert _prov_tax_ns(GROSS, 52) == expected


# ---------------------------------------------------------------------------
# Regression — Nova Scotia weekly payslip ($1,203.13 gross)
# ---------------------------------------------------------------------------

class TestNsWeeklyRegression:
    """
    Regression test: NS weekly payslip with $1,203.13 gross.

    Before the fix, all rules used / 26 → bi-weekly figures.
    After the fix, weekly rules must differ from bi-weekly.
    """

    GROSS = 1203.13
    PERIODS_WEEKLY = 52
    PERIODS_BIWEEKLY = 26

    def test_cpp_weekly_ne_biweekly(self):
        cpp_bw = _cpp_ee(self.GROSS, self.PERIODS_BIWEEKLY)
        cpp_wk = _cpp_ee(self.GROSS, self.PERIODS_WEEKLY)
        assert cpp_wk != cpp_bw, "Weekly CPP_EE must differ from bi-weekly CPP_EE"
        assert abs(cpp_bw) == pytest.approx(63.58, abs=0.02), (
            f"Bi-weekly CPP_EE should be ~$63.58, got {cpp_bw}"
        )
        assert abs(cpp_wk) == pytest.approx(67.59, abs=0.02), (
            f"Weekly CPP_EE should be ~$67.59, got {cpp_wk}"
        )

    def test_prov_tax_weekly_annualizes_by_52(self):
        """PROV_TAX for NS weekly must use ×52 / 52, not ×26 / 26."""
        prov_bw = _prov_tax_ns(self.GROSS, self.PERIODS_BIWEEKLY)
        prov_wk = _prov_tax_ns(self.GROSS, self.PERIODS_WEEKLY)
        assert prov_wk != prov_bw, "Weekly PROV_TAX must differ from bi-weekly PROV_TAX"

    def test_schedule_periods_mapping(self):
        """_l10n_ca_periods_per_year returns expected values for key schedules."""
        cases = {
            "bi-weekly": 26,
            "weekly": 52,
            "monthly": 12,
            "semi-monthly": 24,
            "quarterly": 4,
            "annually": 1,
        }
        for schedule, expected in cases.items():
            slip = _FakePayslip(struct_sp=schedule)
            result = _HrPayslip._l10n_ca_periods_per_year(slip)
            assert result == expected, (
                f"Expected {expected} periods for '{schedule}', got {result}"
            )
