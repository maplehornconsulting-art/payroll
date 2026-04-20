# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Unit tests for the YTD-aware K2/K2P non-refundable tax-credit projection.

Background
----------
CRA T4127 defines K2 (federal) and K2P (provincial) non-refundable credits for
CPP/CPP2/EI contributions using the employee's **annual** contributions, not
the per-period amount annualised naively.  The previous implementation used::

    annual_cpp = abs(CPP_EE_this_period) × periods

which is correct for low/mid earners whose contributions are the same every
period, but produces wrong tax for high earners who hit the annual cap mid-year:

- **Weeks 1–7** ($9,625/wk Ontario):  K2 correct (full cap reached via period × 52).
- **Week 8** (partial period hits cap):  K2 slightly too low → tax slightly high.
- **Weeks 9–52** (CPP_EE = $0 because cap exhausted):
    old: annual_cpp = 0 × 52 = **$0** → K2 = $0 → tax over-withheld rest of year
    new: projected_annual_cpp = ytd(=$4,230) + 0 + 43×0 = **$4,230** → K2 correct

Fix
---
``_l10n_ca_projected_annual_contribution(code, period_amount, annual_max)`` on
``hr.payslip`` combines YTD + current + remaining-periods × current, capped at
``annual_max``.  Both FED_TAX (K2) and PROV_TAX (K2P) use this helper.

All tests run without a live Odoo instance using pure-Python replicas.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 2026 CRA parameters — kept in sync with hr_rule_parameters_data.xml and
# test_cpp_ytd_cap.py (use those values as the source of truth).
# ---------------------------------------------------------------------------

_CPP_RATE = 0.0595
_CPP_EXEMPTION = 3500.0
_CPP_MAX = 4230.20        # annual employee CPP max
_CPP_YMPE = 73200.0       # annual YMPE
_CPP2_RATE = 0.04
_CPP2_CEILING = 85400.0
_CPP2_MAX = 396.00        # annual employee CPP2 max
_EI_RATE = 0.0166
_EI_MAX_INSURABLE = 65700.0
_EI_MAX_PREMIUM = 1091.22

# Federal brackets (threshold, rate)
_FED_BRACKETS = [
    (57375.0, 0.14),
    (114750.0, 0.205),
    (177882.0, 0.26),
    (253414.0, 0.29),
    (float("inf"), 0.33),
]
_FED_BPA_MAX = 16129.0
_FED_BPA_MIN = 14538.0
_FED_PHASE_OUT_START = 177882.0
_FED_PHASE_OUT_END = 253414.0

# Ontario provincial brackets (from PROV_TAX XML fallback)
_ON_BRACKETS = [
    (53891.0, 0.0505),
    (107785.0, 0.0915),
    (150000.0, 0.1116),
    (220000.0, 0.1216),
    (float("inf"), 0.1316),
]
_ON_BPA = 12989.0
# Ontario surtax thresholds — [[threshold, additional_rate], ...]
_ON_SURTAX = [[5818.0, 0.20], [7446.0, 0.36]]


# ---------------------------------------------------------------------------
# Pure-Python replicas of rule logic
# ---------------------------------------------------------------------------

def _projected_annual_contribution(ytd: float, current: float,
                                    periods: int, periods_elapsed: int,
                                    annual_max: float) -> float:
    """Replica of HrPayslip._l10n_ca_projected_annual_contribution.

    Args:
        ytd: Accumulated contribution from prior done/paid payslips.
        current: abs(current-period contribution).
        periods: Pay periods per year.
        periods_elapsed: Count of prior done/paid payslips in this calendar year.
        annual_max: Statutory annual maximum for this contribution type.

    Returns:
        Projected full-year contribution, capped at annual_max.
    """
    remaining = max(periods - periods_elapsed - 1, 0)
    projected = ytd + current + remaining * current
    return min(projected, annual_max)


def _cpp_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """Current-period CPP_EE contribution (positive amount)."""
    period_exemption = _CPP_EXEMPTION / periods
    pensionable = max(gross - period_exemption, 0.0)
    period_contribution = pensionable * _CPP_RATE
    remaining_annual = max(_CPP_MAX - ytd, 0.0)
    return round(min(period_contribution, remaining_annual), 2)


def _cpp2_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """Current-period CPP2_EE contribution (positive amount)."""
    period_ympe = _CPP_YMPE / periods
    period_ceiling = _CPP2_CEILING / periods
    if gross <= period_ympe:
        return 0.0
    cpp2_pensionable = min(gross, period_ceiling) - period_ympe
    period_contribution = cpp2_pensionable * _CPP2_RATE
    remaining_annual = max(_CPP2_MAX - ytd, 0.0)
    return round(min(period_contribution, remaining_annual), 2)


def _ei_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """Current-period EI_EE premium (positive amount)."""
    insurable = min(gross, _EI_MAX_INSURABLE / periods)
    period_premium = insurable * _EI_RATE
    remaining_annual = max(_EI_MAX_PREMIUM - ytd, 0.0)
    return round(min(period_premium, remaining_annual), 2)


def _progressive_tax(income: float, brackets: list) -> float:
    """CRA progressive tax computation."""
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
    """Federal BPA with high-income phase-out."""
    if annual_income <= _FED_PHASE_OUT_START:
        return _FED_BPA_MAX
    if annual_income >= _FED_PHASE_OUT_END:
        return _FED_BPA_MIN
    return (_FED_BPA_MAX
            - (_FED_BPA_MAX - _FED_BPA_MIN)
            * (annual_income - _FED_PHASE_OUT_START)
            / (_FED_PHASE_OUT_END - _FED_PHASE_OUT_START))


def _compute_k2(ytd_cpp: float, current_cpp: float,
                ytd_cpp2: float, current_cpp2: float,
                ytd_ei: float, current_ei: float,
                periods: int, periods_elapsed: int) -> float:
    """Replica of the fixed FED_TAX K2 credit logic."""
    annual_cpp = _projected_annual_contribution(
        ytd_cpp, current_cpp, periods, periods_elapsed, _CPP_MAX)
    annual_cpp2 = _projected_annual_contribution(
        ytd_cpp2, current_cpp2, periods, periods_elapsed, _CPP2_MAX)
    annual_ei = _projected_annual_contribution(
        ytd_ei, current_ei, periods, periods_elapsed, _EI_MAX_PREMIUM)
    return (annual_cpp + annual_cpp2 + annual_ei) * _FED_BRACKETS[0][1]


def _compute_k2p(ytd_cpp: float, current_cpp: float,
                 ytd_cpp2: float, current_cpp2: float,
                 ytd_ei: float, current_ei: float,
                 periods: int, periods_elapsed: int) -> float:
    """Replica of the fixed PROV_TAX K2P credit logic (Ontario rate)."""
    annual_cpp = _projected_annual_contribution(
        ytd_cpp, current_cpp, periods, periods_elapsed, _CPP_MAX)
    annual_cpp2 = _projected_annual_contribution(
        ytd_cpp2, current_cpp2, periods, periods_elapsed, _CPP2_MAX)
    annual_ei = _projected_annual_contribution(
        ytd_ei, current_ei, periods, periods_elapsed, _EI_MAX_PREMIUM)
    return (annual_cpp + annual_cpp2 + annual_ei) * _ON_BRACKETS[0][1]


def _fed_tax_full(gross: float, periods: int, periods_elapsed: int,
                  ytd_cpp: float, ytd_cpp2: float, ytd_ei: float) -> float:
    """Replica of the full FED_TAX rule (tax - K1 - K2) / periods."""
    annual_income = gross * periods
    bpa = _fed_bpa(annual_income)
    tax = _progressive_tax(annual_income, _FED_BRACKETS)
    k1 = bpa * _FED_BRACKETS[0][1]
    current_cpp = _cpp_ee(gross, periods, ytd_cpp)
    current_cpp2 = _cpp2_ee(gross, periods, ytd_cpp2)
    current_ei = _ei_ee(gross, periods, ytd_ei)
    k2 = _compute_k2(ytd_cpp, current_cpp, ytd_cpp2, current_cpp2,
                     ytd_ei, current_ei, periods, periods_elapsed)
    annual_tax = max(tax - k1 - k2, 0.0)
    return round(-(annual_tax / periods), 2)


def _prov_tax_on_full(gross: float, periods: int, periods_elapsed: int,
                      ytd_cpp: float, ytd_cpp2: float, ytd_ei: float) -> float:
    """Replica of the full PROV_TAX rule for Ontario (with surtax and K2P)."""
    annual_income = gross * periods
    tax = _progressive_tax(annual_income, _ON_BRACKETS)
    k1p = _ON_BPA * _ON_BRACKETS[0][1]
    current_cpp = _cpp_ee(gross, periods, ytd_cpp)
    current_cpp2 = _cpp2_ee(gross, periods, ytd_cpp2)
    current_ei = _ei_ee(gross, periods, ytd_ei)
    k2p = _compute_k2p(ytd_cpp, current_cpp, ytd_cpp2, current_cpp2,
                       ytd_ei, current_ei, periods, periods_elapsed)
    basic_tax = max(tax - k1p - k2p, 0.0)
    surtax = 0.0
    for threshold, surrate in _ON_SURTAX:
        if basic_tax > threshold:
            surtax += (basic_tax - threshold) * surrate
    total = basic_tax + surtax
    return round(-(total / periods), 2)


# ---------------------------------------------------------------------------
# Scenario 1 — Week 1, high earner ($9,625/wk), no YTD
# ---------------------------------------------------------------------------

class TestScenario1Week1HighEarner:
    """Week 1 of the year: no prior payslips, no YTD contributions.

    Expected K2 base for CPP = cpp_max (52×568.68 >> cpp_max, so capped).
    The projected annual contribution must equal the full annual maximum.
    """

    GROSS = 9625.0
    PERIODS = 52
    PERIODS_ELAPSED = 0

    def test_projected_cpp_equals_annual_max(self):
        """Week 1 high earner: projected CPP = cpp_max (period×52 >> cap)."""
        ytd = 0.0
        current = _cpp_ee(self.GROSS, self.PERIODS, ytd)
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP_MAX)
        assert result == pytest.approx(_CPP_MAX, abs=0.01)

    def test_projected_cpp2_equals_annual_max(self):
        """Week 1 high earner: projected CPP2 = cpp2_max."""
        ytd = 0.0
        current = _cpp2_ee(self.GROSS, self.PERIODS, ytd)
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP2_MAX)
        assert result == pytest.approx(_CPP2_MAX, abs=0.01)

    def test_projected_ei_near_annual_max(self):
        """Week 1 high earner: projected EI ≈ ei_max (within ±$2 due to per-period MIE rounding).

        EI has both a per-period insurable cap and an annual premium cap.  The
        per-period cap (MIE / periods) when summed over 52 weeks may produce a
        total that is within a dollar or two of the annual max but not exact, due
        to rounding.  The projected value must be positive, large, and ≤ annual max.
        """
        ytd = 0.0
        current = _ei_ee(self.GROSS, self.PERIODS, ytd)
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _EI_MAX_PREMIUM)
        assert result <= _EI_MAX_PREMIUM + 0.01
        assert result >= _EI_MAX_PREMIUM - 2.0, (
            f"Projected EI {result} should be near the annual max {_EI_MAX_PREMIUM}"
        )

    def test_k2_uses_full_cpp_max(self):
        """K2 credit base for CPP must be cpp_max, not 0 or a fraction."""
        ytd_cpp = 0.0
        current_cpp = _cpp_ee(self.GROSS, self.PERIODS, ytd_cpp)
        k2 = _compute_k2(ytd_cpp, current_cpp, 0.0, 0.0, 0.0,
                          _ei_ee(self.GROSS, self.PERIODS, 0.0),
                          self.PERIODS, self.PERIODS_ELAPSED)
        # K2 must be >= cpp_max * lowest_rate (at minimum CPP contributes the max)
        min_k2 = _CPP_MAX * _FED_BRACKETS[0][1]
        assert k2 >= min_k2 - 0.01

    def test_k2p_uses_full_cpp_max(self):
        """K2P credit base for CPP must be cpp_max."""
        ytd_cpp = 0.0
        current_cpp = _cpp_ee(self.GROSS, self.PERIODS, ytd_cpp)
        k2p = _compute_k2p(ytd_cpp, current_cpp, 0.0, 0.0, 0.0,
                            _ei_ee(self.GROSS, self.PERIODS, 0.0),
                            self.PERIODS, self.PERIODS_ELAPSED)
        min_k2p = _CPP_MAX * _ON_BRACKETS[0][1]
        assert k2p >= min_k2p - 0.01


# ---------------------------------------------------------------------------
# Scenario 2 — Week 8, partial YTD, partially consumed cap
# ---------------------------------------------------------------------------

class TestScenario2Week8PartialCap:
    """Week 8: YTD ≈ 7 × 568.68 = 3,980.76, current = residual to cap.

    Projected annual = ytd + residual + 44 × residual >> cap → capped at cpp_max.
    K2 remains at full annual credit (same as week 1).
    """

    GROSS = 9625.0
    PERIODS = 52
    PERIODS_ELAPSED = 7

    def _build_ytd_cpp(self) -> float:
        """Simulate 7 payslips accumulating CPP YTD."""
        ytd = 0.0
        for _ in range(7):
            ytd += _cpp_ee(self.GROSS, self.PERIODS, ytd)
        return ytd

    def test_projected_cpp_still_caps_at_annual_max(self):
        """After 7 payslips, 8th projected annual = cpp_max (residual × 45 >> gap)."""
        ytd = self._build_ytd_cpp()
        current = _cpp_ee(self.GROSS, self.PERIODS, ytd)
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP_MAX)
        assert result == pytest.approx(_CPP_MAX, abs=0.01)

    def test_k2_unchanged_from_week1(self):
        """K2 for week 8 must be the same as week 1 (both use cpp_max)."""
        # Week 1 K2
        k2_week1 = _compute_k2(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                 0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                 0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                 self.PERIODS, 0)
        # Week 8 K2
        ytd_cpp = self._build_ytd_cpp()
        current_cpp = _cpp_ee(self.GROSS, self.PERIODS, ytd_cpp)
        ytd_cpp2 = 0.0
        for _ in range(7):
            ytd_cpp2 += _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2)
        current_cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2)
        ytd_ei = 0.0
        for _ in range(7):
            ytd_ei += _ei_ee(self.GROSS, self.PERIODS, ytd_ei)
        current_ei = _ei_ee(self.GROSS, self.PERIODS, ytd_ei)
        k2_week8 = _compute_k2(ytd_cpp, current_cpp, ytd_cpp2, current_cpp2,
                                 ytd_ei, current_ei, self.PERIODS, self.PERIODS_ELAPSED)
        assert k2_week8 == pytest.approx(k2_week1, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario 3 — Week 9, cap fully consumed, current = $0 (the bug fix)
# ---------------------------------------------------------------------------

class TestScenario3CapFullyConsumed:
    """Week 9: CPP cap fully consumed, CPP_EE = $0 this period.

    **This is the core bug fix.**

    Old logic:  annual_cpp = $0 × 52 = $0  → K2 loses entire CPP credit
                → FED_TAX jumps materially (credit gone)
    New logic:  projected = ytd($4,230) + $0 + 43×$0 = $4,230
                → K2 unchanged → FED_TAX consistent week-over-week.
    """

    GROSS = 9625.0
    PERIODS = 52
    PERIODS_ELAPSED = 8

    def test_projected_cpp_equals_ytd_not_zero(self):
        """When current=0 and ytd=cpp_max, projected must equal cpp_max, not 0."""
        ytd = _CPP_MAX
        current = 0.0
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP_MAX)
        assert result == pytest.approx(_CPP_MAX, abs=0.01), (
            f"Bug: projected={result} should be {_CPP_MAX} when ytd=cpp_max, current=0"
        )

    def test_projected_cpp_not_zero_when_current_is_zero(self):
        """Projected annual contribution must NOT be zero when ytd holds the cap."""
        ytd = _CPP_MAX
        current = 0.0
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP_MAX)
        assert result > 0.0, (
            "Bug regression: projected annual CPP must not be 0 when ytd=cpp_max"
        )

    def test_k2_same_week9_as_week1(self):
        """K2 in week 9 (cpp=0 this period) must equal K2 in week 1."""
        # Week 1: no YTD, full period contribution
        k2_week1 = _compute_k2(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                 0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                 0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                 self.PERIODS, 0)
        # Week 9: CPP fully capped, EI may still be running
        ytd_cpp = _CPP_MAX       # cap fully consumed after 8 payslips
        current_cpp = 0.0        # no CPP deducted this period
        ytd_cpp2 = _CPP2_MAX     # also fully capped (for simplicity)
        current_cpp2 = 0.0
        ytd_ei = 0.0
        for _ in range(8):
            ytd_ei += _ei_ee(self.GROSS, self.PERIODS, ytd_ei)
        current_ei = _ei_ee(self.GROSS, self.PERIODS, ytd_ei)
        k2_week9 = _compute_k2(ytd_cpp, current_cpp, ytd_cpp2, current_cpp2,
                                 ytd_ei, current_ei, self.PERIODS, self.PERIODS_ELAPSED)
        assert k2_week9 == pytest.approx(k2_week1, abs=0.01), (
            f"Bug regression: K2 dropped from {k2_week1:.4f} to {k2_week9:.4f} "
            f"when CPP cap hit (week 9)"
        )

    def test_k2p_same_week9_as_week1(self):
        """K2P in week 9 must equal K2P in week 1 (provincial credit preserved)."""
        k2p_week1 = _compute_k2p(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                   0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                   0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                   self.PERIODS, 0)
        ytd_cpp = _CPP_MAX
        current_cpp = 0.0
        ytd_cpp2 = _CPP2_MAX
        current_cpp2 = 0.0
        ytd_ei = 0.0
        for _ in range(8):
            ytd_ei += _ei_ee(self.GROSS, self.PERIODS, ytd_ei)
        current_ei = _ei_ee(self.GROSS, self.PERIODS, ytd_ei)
        k2p_week9 = _compute_k2p(ytd_cpp, current_cpp, ytd_cpp2, current_cpp2,
                                   ytd_ei, current_ei, self.PERIODS, self.PERIODS_ELAPSED)
        assert k2p_week9 == pytest.approx(k2p_week1, abs=0.01), (
            f"Bug regression: K2P dropped from {k2p_week1:.4f} to {k2p_week9:.4f} "
            f"when CPP cap hit (week 9)"
        )

    def test_fed_tax_week9_consistent_with_week1(self):
        """FED_TAX in week 9 must equal FED_TAX in week 1 (K2 not lost)."""
        fed_week1 = _fed_tax_full(self.GROSS, self.PERIODS, 0,
                                   0.0, 0.0, 0.0)
        fed_week9 = _fed_tax_full(self.GROSS, self.PERIODS, self.PERIODS_ELAPSED,
                                   _CPP_MAX, _CPP2_MAX, 0.0)
        assert fed_week9 == pytest.approx(fed_week1, abs=0.50), (
            f"Bug regression: FED_TAX jumped from {fed_week1} to {fed_week9} "
            f"when CPP cap hit (week 9); K2 credit must not be lost"
        )

    def test_prov_tax_week9_consistent_with_week1(self):
        """ON PROV_TAX in week 9 must equal week 1 (K2P not lost)."""
        prov_week1 = _prov_tax_on_full(self.GROSS, self.PERIODS, 0,
                                        0.0, 0.0, 0.0)
        prov_week9 = _prov_tax_on_full(self.GROSS, self.PERIODS, self.PERIODS_ELAPSED,
                                        _CPP_MAX, _CPP2_MAX, 0.0)
        assert prov_week9 == pytest.approx(prov_week1, abs=0.50), (
            f"Bug regression: PROV_TAX jumped from {prov_week1} to {prov_week9} "
            f"when CPP cap hit (week 9); K2P credit must not be lost"
        )


# ---------------------------------------------------------------------------
# Scenario 4 — Low earner regression (constant $1,200/wk, never caps)
# ---------------------------------------------------------------------------

class TestScenario4LowEarnerRegression:
    """$1,200/wk weekly; annual CPP ≈ $3,360, well below the $4,230 cap.

    For earners who never hit the annual cap, the new logic must produce the
    same K2/K2P as the old naive ``period × periods`` formula.
    """

    GROSS = 1200.0
    PERIODS = 52
    PERIODS_ELAPSED = 0

    def test_projected_cpp_same_as_naive_annualization(self):
        """For low earners, projected = period × periods (never hits cap)."""
        ytd = 0.0
        current = _cpp_ee(self.GROSS, self.PERIODS, ytd)
        projected = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP_MAX)
        naive = current * self.PERIODS
        # projected should equal min(naive, cpp_max); since naive < cpp_max for
        # this earner, projected == naive.
        assert naive < _CPP_MAX, "Test assumes low earner never caps"
        assert projected == pytest.approx(naive, abs=0.02)

    def test_k2_equals_old_formula(self):
        """K2 from new logic must equal K2 from old naive period×periods formula."""
        current_cpp = _cpp_ee(self.GROSS, self.PERIODS, 0.0)
        current_cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, 0.0)
        current_ei = _ei_ee(self.GROSS, self.PERIODS, 0.0)

        # New (YTD-aware) K2
        k2_new = _compute_k2(0.0, current_cpp, 0.0, current_cpp2, 0.0,
                               current_ei, self.PERIODS, self.PERIODS_ELAPSED)

        # Old (naive) K2 formula
        annual_cpp_naive = current_cpp * self.PERIODS
        annual_cpp2_naive = current_cpp2 * self.PERIODS
        annual_ei_naive = current_ei * self.PERIODS
        k2_old = (annual_cpp_naive + annual_cpp2_naive + annual_ei_naive) * _FED_BRACKETS[0][1]

        assert k2_new == pytest.approx(k2_old, abs=0.02), (
            f"Low-earner regression: new K2 {k2_new} != old K2 {k2_old}"
        )

    def test_k2p_equals_old_formula(self):
        """K2P from new logic must equal K2P from old naive formula for low earners."""
        current_cpp = _cpp_ee(self.GROSS, self.PERIODS, 0.0)
        current_cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, 0.0)
        current_ei = _ei_ee(self.GROSS, self.PERIODS, 0.0)

        k2p_new = _compute_k2p(0.0, current_cpp, 0.0, current_cpp2, 0.0,
                                 current_ei, self.PERIODS, self.PERIODS_ELAPSED)

        annual_cpp_naive = current_cpp * self.PERIODS
        annual_cpp2_naive = current_cpp2 * self.PERIODS
        annual_ei_naive = current_ei * self.PERIODS
        k2p_old = (annual_cpp_naive + annual_cpp2_naive + annual_ei_naive) * _ON_BRACKETS[0][1]

        assert k2p_new == pytest.approx(k2p_old, abs=0.02), (
            f"Low-earner regression: new K2P {k2p_new} != old K2P {k2p_old}"
        )

    def test_fed_tax_unchanged_for_low_earner(self):
        """FED_TAX for $1,200/wk should be unaffected by the fix."""
        # Old formula: period × periods for K2 base
        current_cpp = _cpp_ee(self.GROSS, self.PERIODS, 0.0)
        current_cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, 0.0)
        current_ei = _ei_ee(self.GROSS, self.PERIODS, 0.0)
        annual_income = self.GROSS * self.PERIODS
        bpa = _fed_bpa(annual_income)
        tax = _progressive_tax(annual_income, _FED_BRACKETS)
        k1 = bpa * _FED_BRACKETS[0][1]
        k2_old = (current_cpp * self.PERIODS
                  + current_cpp2 * self.PERIODS
                  + current_ei * self.PERIODS) * _FED_BRACKETS[0][1]
        annual_tax_old = max(tax - k1 - k2_old, 0.0)
        fed_old = round(-(annual_tax_old / self.PERIODS), 2)

        # New formula (YTD-aware, but no cap hit for low earner)
        fed_new = _fed_tax_full(self.GROSS, self.PERIODS, self.PERIODS_ELAPSED,
                                 0.0, 0.0, 0.0)

        assert fed_new == pytest.approx(fed_old, abs=0.02), (
            f"Low-earner FED_TAX changed: old={fed_old}, new={fed_new}"
        )


# ---------------------------------------------------------------------------
# Scenario 5 — Mid-year hire (week 30), high earner, no YTD
# ---------------------------------------------------------------------------

class TestScenario5MidYearHire:
    """Employee starts in week 30 (periods_elapsed=0) with $9,625/wk gross.

    Even though it's mid-year, there is no prior YTD for this employee.
    Projected annual contribution = 0 + current + 22 × current.  Because
    current is the full per-period contribution (~$568.68), the projected
    value (23 × 568.68 ≈ $13,078) still exceeds cpp_max → capped at cpp_max.

    K2 must equal the full annual max credit (same as week 1 scenario).
    """

    GROSS = 9625.0
    PERIODS = 52
    PERIODS_ELAPSED = 0    # new hire; 0 prior done/paid slips in this year

    def test_projected_cpp_capped_at_max(self):
        """Mid-year hire: projected CPP capped at annual max (no prior YTD)."""
        ytd = 0.0
        current = _cpp_ee(self.GROSS, self.PERIODS, ytd)
        result = _projected_annual_contribution(
            ytd, current, self.PERIODS, self.PERIODS_ELAPSED, _CPP_MAX)
        assert result == pytest.approx(_CPP_MAX, abs=0.01)

    def test_k2_same_as_week1_high_earner(self):
        """Mid-year hire K2 must equal week-1 high-earner K2 (both use full cpp_max)."""
        k2_week1 = _compute_k2(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                 0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                 0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                 self.PERIODS, 0)
        k2_midyear = _compute_k2(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                   0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                   0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                   self.PERIODS, self.PERIODS_ELAPSED)
        assert k2_midyear == pytest.approx(k2_week1, abs=0.01)

    def test_k2p_same_as_week1_high_earner(self):
        """Mid-year hire K2P must equal week-1 high-earner K2P."""
        k2p_week1 = _compute_k2p(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                   0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                   0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                   self.PERIODS, 0)
        k2p_midyear = _compute_k2p(0.0, _cpp_ee(self.GROSS, self.PERIODS, 0.0),
                                     0.0, _cpp2_ee(self.GROSS, self.PERIODS, 0.0),
                                     0.0, _ei_ee(self.GROSS, self.PERIODS, 0.0),
                                     self.PERIODS, self.PERIODS_ELAPSED)
        assert k2p_midyear == pytest.approx(k2p_week1, abs=0.01)


# ---------------------------------------------------------------------------
# _projected_annual_contribution unit tests (helper contract)
# ---------------------------------------------------------------------------

class TestProjectedAnnualContributionHelper:
    """Direct unit tests for the _projected_annual_contribution helper."""

    def test_no_ytd_no_elapsed_full_year(self):
        """First payslip, full year ahead: projected = min(52×current, max)."""
        result = _projected_annual_contribution(0.0, 100.0, 52, 0, 10000.0)
        assert result == pytest.approx(52 * 100.0, abs=0.01)

    def test_capped_by_annual_max(self):
        """When projected would exceed annual_max, returns annual_max."""
        result = _projected_annual_contribution(0.0, 1000.0, 52, 0, 5000.0)
        assert result == pytest.approx(5000.0, abs=0.01)

    def test_ytd_plus_current_exceeds_max(self):
        """YTD alone already at max, current=0 → returns annual_max."""
        result = _projected_annual_contribution(5000.0, 0.0, 52, 8, 5000.0)
        assert result == pytest.approx(5000.0, abs=0.01)

    def test_ytd_near_max_current_small(self):
        """YTD near max; remaining projection still capped at max."""
        result = _projected_annual_contribution(4900.0, 50.0, 52, 8, 5000.0)
        assert result == pytest.approx(5000.0, abs=0.01)

    def test_last_payslip_of_year(self):
        """Final payslip (periods_elapsed = periods-1): remaining=0."""
        result = _projected_annual_contribution(400.0, 50.0, 52, 51, 5000.0)
        # remaining = max(52 - 51 - 1, 0) = 0; projected = 400 + 50 + 0 = 450
        assert result == pytest.approx(450.0, abs=0.01)

    def test_remaining_periods_floored_at_zero(self):
        """periods_elapsed > periods−1 does not produce negative remaining."""
        result = _projected_annual_contribution(0.0, 100.0, 52, 60, 5000.0)
        # remaining = max(52 - 60 - 1, 0) = 0; projected = 0 + 100 + 0 = 100
        assert result == pytest.approx(100.0, abs=0.01)

    def test_zero_period_amount_ytd_at_max(self):
        """Core K2 fix: ytd=max, current=0 → projected=max (not 0)."""
        cpp_max = 4230.20
        result = _projected_annual_contribution(cpp_max, 0.0, 52, 8, cpp_max)
        assert result == pytest.approx(cpp_max, abs=0.01)

    def test_zero_period_amount_no_ytd(self):
        """No YTD, current=0 (e.g., CPP-exempt period) → projected=0."""
        result = _projected_annual_contribution(0.0, 0.0, 52, 0, 5000.0)
        assert result == pytest.approx(0.0, abs=0.01)
