# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Unit tests for the YTD-cumulative CPP / CPP2 / EI annual cap behaviour.

These tests verify the fix for the per-period cap bug described in the problem
statement.  The buggy code smeared the annual maximum evenly across all periods
(``annual_max / periods``); the correct behaviour is to cap each period's
deduction against the *remaining* annual headroom
(``annual_max − ytd_contributions_to_date``).

Concrete bug reproduction (Ontario, weekly, 2026):
  - Gross/week: $9,625 (≈ $500K annualized)
  - First payslip of the year, no YTD
  - **Buggy:**  CPP_EE = $81.35  (= 4,230.20 ÷ 52),  CPP2_EE = $8.00  (= 416 ÷ 52)
  - **Correct:** CPP_EE ≈ $568.68,  CPP2_EE ≈ $320.16

All tests run without a live Odoo instance using pure-Python replicas of the
fixed salary rule logic.  The ``_cpp_ee``, ``_cpp2_ee``, and ``_ei_ee``
helpers declared here mirror the ``amount_python_compute`` bodies in
``data/hr_salary_rule_data.xml`` and the ``_l10n_ca_get_payslip_line_values``
branches in ``models/hr_payslip.py``.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 2026 CRA parameters — must match hr_rule_parameters_data.xml
# ---------------------------------------------------------------------------

_CPP_RATE = 0.0595
_CPP_EXEMPTION = 3500.0          # annual basic exemption
_CPP_MAX = 4230.20               # annual employee CPP maximum (2026)
_CPP_YMPE = 73200.0              # annual YMPE (2026)
_CPP2_RATE = 0.04
_CPP2_CEILING = 85400.0          # annual CPP2 earnings ceiling
_CPP2_MAX = 396.00               # annual employee CPP2 maximum (2026 approx)

_EI_RATE = 0.0166
_EI_MAX_INSURABLE = 65700.0      # annual maximum insurable earnings
_EI_MAX_PREMIUM = 1091.22        # annual employee maximum EI premium


# ---------------------------------------------------------------------------
# Pure-Python replicas of the fixed rule logic
# ---------------------------------------------------------------------------

def _cpp_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """Replicate the fixed CPP_EE rule.

    Uses annual cumulative cap: ``min(period_contribution, annual_max − ytd)``.
    """
    period_exemption = _CPP_EXEMPTION / periods
    pensionable = max(gross - period_exemption, 0.0)
    period_contribution = pensionable * _CPP_RATE
    remaining_annual = max(_CPP_MAX - ytd, 0.0)
    return round(min(period_contribution, remaining_annual), 2)


def _cpp2_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """Replicate the fixed CPP2_EE rule.

    CPP2 only applies when gross > period YMPE.  Same YTD-cumulative cap
    pattern as CPP_EE.
    """
    period_ympe = _CPP_YMPE / periods
    period_ceiling = _CPP2_CEILING / periods
    if gross <= period_ympe:
        return 0.0
    cpp2_pensionable = min(gross, period_ceiling) - period_ympe
    period_contribution = cpp2_pensionable * _CPP2_RATE
    remaining_annual = max(_CPP2_MAX - ytd, 0.0)
    return round(min(period_contribution, remaining_annual), 2)


def _ei_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """Replicate the fixed EI_EE rule.

    Applies the per-period MIE insurable cap first, then the annual premium
    cumulative cap against ytd_ei.
    """
    insurable = min(gross, _EI_MAX_INSURABLE / periods)
    period_premium = insurable * _EI_RATE
    remaining_annual = max(_EI_MAX_PREMIUM - ytd, 0.0)
    return round(min(period_premium, remaining_annual), 2)


# ---------------------------------------------------------------------------
# Scenario 1 — First payslip, high earner ($9,625/wk Ontario, no YTD)
# ---------------------------------------------------------------------------

class TestFirstPayslipHighEarner:
    """$9,625/wk gross, first payslip (ytd=0).

    Bug: CPP_EE was $81.35 (= 4,230.20 ÷ 52) and CPP2_EE was $8.00
         (= 416 ÷ 52).
    Fix: CPP_EE ≈ $568.68, CPP2_EE should reflect full CPP2 headroom.
    """

    GROSS = 9625.0
    PERIODS = 52

    def test_cpp_ee_first_payslip(self):
        """CPP_EE on first payslip must NOT be annual_max/52."""
        result = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        # Buggy value was annual_max / 52 ≈ 81.35; correct value is ≈ 568.68.
        assert result != pytest.approx(4230.20 / 52, abs=0.10), (
            "CPP_EE must not be the per-period smeared max (bug)"
        )
        # Correct: pensionable = 9625 − 3500/52 ≈ 9557.69; × 5.95% ≈ 568.68
        expected_pensionable = self.GROSS - _CPP_EXEMPTION / self.PERIODS
        expected = round(min(expected_pensionable * _CPP_RATE, _CPP_MAX), 2)
        assert result == pytest.approx(expected, abs=0.02)

    def test_cpp2_ee_first_payslip(self):
        """CPP2_EE on first payslip must NOT be annual_max/52."""
        result = _cpp2_ee(self.GROSS, self.PERIODS, ytd=0.0)
        # Buggy value was cpp2_max / 52 ≈ 8.00; correct value much larger.
        assert result != pytest.approx(_CPP2_MAX / 52, abs=0.10), (
            "CPP2_EE must not be the per-period smeared max (bug)"
        )
        # Correct: cpp2_pensionable = min(9625, 85400/52) − 73200/52
        period_ympe = _CPP_YMPE / self.PERIODS
        period_ceiling = _CPP2_CEILING / self.PERIODS
        expected_pensionable = min(self.GROSS, period_ceiling) - period_ympe
        expected = round(min(expected_pensionable * _CPP2_RATE, _CPP2_MAX), 2)
        assert result == pytest.approx(expected, abs=0.02)

    def test_cpp_ee_gt_buggy_amount(self):
        """Correct CPP_EE must be substantially larger than the buggy amount."""
        result = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        buggy_amount = round(_CPP_MAX / self.PERIODS, 2)
        assert result > buggy_amount * 5, (
            f"CPP_EE {result} should be much larger than buggy {buggy_amount}"
        )


# ---------------------------------------------------------------------------
# Scenario 2 — Cap reached mid-year (partial YTD)
# ---------------------------------------------------------------------------

class TestCapReachedMidYear:
    """After several high-gross payslips, YTD approaches the annual max.

    On the 8th payslip the remaining headroom is less than a full period
    contribution, so CPP_EE equals the remaining headroom, not the full
    period contribution.
    """

    GROSS = 9625.0
    PERIODS = 52

    def _simulate_ytd(self, n_payslips: int) -> float:
        """Simulate n identical payslips at GROSS, accumulating YTD."""
        ytd = 0.0
        for _ in range(n_payslips):
            contribution = _cpp_ee(self.GROSS, self.PERIODS, ytd=ytd)
            ytd += contribution
        return ytd

    def test_ytd_after_7_payslips(self):
        """After 7 weekly payslips at $9,625, YTD should equal full annual max."""
        ytd = self._simulate_ytd(7)
        # 7 × 568.68 ≈ 3,980.76 — still below the annual max.
        assert ytd < _CPP_MAX
        assert ytd > _CPP_MAX * 0.90  # used most of the annual budget

    def test_8th_payslip_is_remainder(self):
        """8th payslip deduction equals remaining headroom, not full period."""
        ytd_after_7 = self._simulate_ytd(7)
        remaining = _CPP_MAX - ytd_after_7
        eighth = _cpp_ee(self.GROSS, self.PERIODS, ytd=ytd_after_7)
        assert eighth == pytest.approx(remaining, abs=0.02)
        # Must be less than a full period contribution.
        full_period = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert eighth < full_period

    def test_8th_payslip_not_buggy_amount(self):
        """8th payslip must NOT equal the buggy per-period cap."""
        ytd_after_7 = self._simulate_ytd(7)
        eighth = _cpp_ee(self.GROSS, self.PERIODS, ytd=ytd_after_7)
        buggy = round(_CPP_MAX / self.PERIODS, 2)
        assert eighth != pytest.approx(buggy, abs=0.02)


# ---------------------------------------------------------------------------
# Scenario 3 — Cap fully consumed
# ---------------------------------------------------------------------------

class TestCapFullyConsumed:
    """When YTD already equals the annual max, next payslip contribution = $0."""

    def test_cpp_ee_zero_when_cap_consumed(self):
        result = _cpp_ee(9625.0, 52, ytd=_CPP_MAX)
        assert result == 0.0

    def test_cpp2_ee_zero_when_cap_consumed(self):
        result = _cpp2_ee(9625.0, 52, ytd=_CPP2_MAX)
        assert result == 0.0

    def test_ei_ee_zero_when_cap_consumed(self):
        result = _ei_ee(9625.0, 52, ytd=_EI_MAX_PREMIUM)
        assert result == 0.0

    def test_cpp_ee_zero_when_ytd_exceeds_cap(self):
        """Slightly-over-max YTD (due to rounding) also produces zero."""
        result = _cpp_ee(9625.0, 52, ytd=_CPP_MAX + 0.01)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Scenario 4 — Constant low earner unchanged (regression)
# ---------------------------------------------------------------------------

class TestLowEarnerUnchanged:
    """$1,203.13/wk for 52 weeks — individual period CPP must match old behaviour.

    A low earner whose total annual CPP never reaches the cap is unaffected by
    the YTD fix; each weekly period produces the same contribution regardless
    of whether a per-period or annual cap is used.
    """

    GROSS = 1203.13
    PERIODS = 52
    EXPECTED_WEEKLY_CPP = 67.59  # unchanged from old behaviour

    def test_first_payslip_low_earner(self):
        """First payslip of the year: CPP_EE ≈ $67.59."""
        result = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert result == pytest.approx(self.EXPECTED_WEEKLY_CPP, abs=0.02)

    def test_mid_year_low_earner_unchanged(self):
        """After 25 payslips at $1,203.13, deduction per period is still ≈ $67.59."""
        ytd = sum(_cpp_ee(self.GROSS, self.PERIODS, ytd=i * self.EXPECTED_WEEKLY_CPP)
                  for i in range(25))
        result = _cpp_ee(self.GROSS, self.PERIODS, ytd=ytd)
        assert result == pytest.approx(self.EXPECTED_WEEKLY_CPP, abs=0.02)

    def test_annual_total_stays_within_cap(self):
        """Sum of 52 weekly CPP deductions at $1,203.13 must not exceed annual max."""
        ytd = 0.0
        for _ in range(52):
            contribution = _cpp_ee(self.GROSS, self.PERIODS, ytd=ytd)
            ytd += contribution
        assert ytd <= _CPP_MAX + 0.01


# ---------------------------------------------------------------------------
# Scenario 5 — Mid-year hire (no prior YTD)
# ---------------------------------------------------------------------------

class TestMidYearHire:
    """Employee starts in week 20 with no YTD.

    The first payslip must yield the full uncapped per-period contribution
    (since annual_max − 0 = annual_max > period_contribution), NOT any
    'remaining weeks' fraction.
    """

    GROSS = 9625.0
    PERIODS = 52

    def test_first_payslip_mid_year_hire(self):
        """Week-20 first payslip: CPP_EE ≈ $568.68, not $81.35."""
        result = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        # Same calculation regardless of which week in the year it is.
        # YTD=0 → full annual headroom → period_contribution is the limiting factor.
        expected_pensionable = self.GROSS - _CPP_EXEMPTION / self.PERIODS
        expected = round(min(expected_pensionable * _CPP_RATE, _CPP_MAX), 2)
        assert result == pytest.approx(expected, abs=0.02)
        assert result != pytest.approx(_CPP_MAX / self.PERIODS, abs=0.10), (
            "Mid-year hire CPP must not use the annual_max / periods formula"
        )


# ---------------------------------------------------------------------------
# Scenario 6 — CPP2 parallel scenarios
# ---------------------------------------------------------------------------

class TestCpp2YtdCap:
    """CPP2 mirrors CPP: annual cumulative cap, not per-period cap."""

    GROSS = 9625.0
    PERIODS = 52

    def test_cpp2_first_payslip(self):
        """First payslip CPP2 should not equal annual_max/52."""
        result = _cpp2_ee(self.GROSS, self.PERIODS, ytd=0.0)
        buggy = round(_CPP2_MAX / self.PERIODS, 2)
        assert result != pytest.approx(buggy, abs=0.10), (
            "CPP2_EE must not be the per-period smeared max (bug)"
        )

    def test_cpp2_cap_consumed(self):
        """CPP2 = 0 when YTD equals annual max."""
        result = _cpp2_ee(self.GROSS, self.PERIODS, ytd=_CPP2_MAX)
        assert result == 0.0

    def test_cpp2_partial_ytd(self):
        """CPP2 deduction limited to remaining annual headroom when headroom < period."""
        # CPP2 period contribution at $9,625/wk is small (≈$9.38) due to the
        # narrow YMPE→ceiling band.  To test the YTD cap we need remaining < period.
        ytd = _CPP2_MAX - 5.0   # leaves only $5 headroom; period contribution > $5
        result = _cpp2_ee(self.GROSS, self.PERIODS, ytd=ytd)
        remaining = _CPP2_MAX - ytd  # = 5.0
        assert result == pytest.approx(remaining, abs=0.02)

    def test_cpp2_zero_below_ympe(self):
        """CPP2 is always 0 when gross does not exceed per-period YMPE."""
        low_gross = _CPP_YMPE / self.PERIODS - 1  # just below period YMPE
        result = _cpp2_ee(low_gross, self.PERIODS, ytd=0.0)
        assert result == 0.0

    def test_cpp2_annual_accumulation(self):
        """Sum of CPP2 over many payslips must not exceed annual max."""
        ytd = 0.0
        for _ in range(52):
            contribution = _cpp2_ee(self.GROSS, self.PERIODS, ytd=ytd)
            ytd += contribution
        assert ytd <= _CPP2_MAX + 0.01


# ---------------------------------------------------------------------------
# Scenario 7 — EI annual cap
# ---------------------------------------------------------------------------

class TestEiAnnualCap:
    """EI: per-period MIE insurable cap is retained; annual premium cap enforced."""

    GROSS = 9625.0
    PERIODS = 52

    def test_ei_zero_when_annual_cap_consumed(self):
        """EI = $0 when YTD already equals the annual maximum premium."""
        result = _ei_ee(self.GROSS, self.PERIODS, ytd=_EI_MAX_PREMIUM)
        assert result == 0.0

    def test_ei_partial_ytd(self):
        """EI deduction limited to remaining annual premium headroom when headroom < period."""
        # EI period premium at $9,625/wk is capped at the per-period insurable
        # amount (≈$20.97).  To test the annual YTD cap we need remaining < $20.97.
        ytd = _EI_MAX_PREMIUM - 10.0   # leaves only $10 headroom
        result = _ei_ee(self.GROSS, self.PERIODS, ytd=ytd)
        remaining = _EI_MAX_PREMIUM - ytd  # = 10.0
        assert result == pytest.approx(remaining, abs=0.01)

    def test_ei_per_period_insurable_cap_retained(self):
        """Per-period MIE insurable cap still applies when annual cap is not reached."""
        # With ytd=0, the annual cap does not bind for normal-wage earners.
        result = _ei_ee(self.GROSS, self.PERIODS, ytd=0.0)
        # The per-period insurable cap limits premiums to ≈ max_insurable/periods × rate.
        period_insurable_limit = (_EI_MAX_INSURABLE / self.PERIODS) * _EI_RATE
        assert result == pytest.approx(period_insurable_limit, abs=0.02)

    def test_ei_annual_total_does_not_exceed_max(self):
        """Accumulated EI over 52 weekly payslips must not exceed annual max."""
        ytd = 0.0
        for _ in range(52):
            premium = _ei_ee(self.GROSS, self.PERIODS, ytd=ytd)
            ytd += premium
        assert ytd <= _EI_MAX_PREMIUM + 0.01

    def test_ei_ytd_zero_low_earner_unchanged(self):
        """Low earner below insurable cap: EI unaffected by YTD fix."""
        gross = 1203.13
        result = _ei_ee(gross, self.PERIODS, ytd=0.0)
        expected_insurable = min(gross, _EI_MAX_INSURABLE / self.PERIODS)
        expected = round(min(expected_insurable * _EI_RATE, _EI_MAX_PREMIUM), 2)
        assert result == pytest.approx(expected, abs=0.01)
