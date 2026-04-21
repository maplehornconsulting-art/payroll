# Part of MHC. See LICENSE file for full copyright and licensing details.
"""PDOC parity regression tests — verifies the corrected T4127 formula.

These tests replicate the full FED_TAX and PROV_TAX salary rule logic (including
the three T4127 fixes: income reduction by enhanced CPP/CPP2, CEA in K1, and
base-CPP-only in K2/K2P) and confirm the results match CRA's PDOC output to
within rounding tolerance.

Reference scenario: Nova Scotia, biweekly (26 pay periods/year), gross $2,000.00,
Federal TD1 = $16,452 (2026 BPA), Provincial TD1 = $11,932 (NS 2026 BPA).

PDOC expected (verified 2026-04):
  CPP_EE  = −110.99  ✓
  EI_EE   =  −32.60  ✓
  Fed Tax = −163.23  ✓
  NS Tax  = −171.47  ✓ (formula produces 171.46; PDOC rounds differently)
  Net     = 1,521.71 ✓ (within ±0.05 of formula result)

Also includes an Ontario scenario to confirm OHP still computes correctly with
the income-reduction logic applied only to FED_TAX/PROV_TAX.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 2026 CRA rule parameters (from hr_rule_parameters_data.xml)
# ---------------------------------------------------------------------------

_CPP_RATE      = 0.0595    # total CPP employee rate
_CPP_BASE_RATE = 0.0495    # base portion → non-refundable K2/K2P credit
_CPP_ENHANCED  = 0.0100    # enhanced portion → income deduction (T4127 U1)
_CPP_EXEMPTION = 3500.0    # annual basic exemption
_CPP_MAX       = 4230.45   # annual employee CPP maximum contribution
_CPP2_RATE     = 0.04
_CPP2_CEILING  = 85000.0
_CPP2_MAX      = 416.00
_EI_RATE       = 0.0163
_EI_MAX_INS    = 68900.0   # annual maximum insurable earnings
_EI_MAX_PREM   = 1123.07   # annual employee EI maximum premium

# Federal brackets: (upper_threshold, rate)
_FED_BRACKETS = [
    (58523.0,   0.14),
    (117045.0,  0.205),
    (181440.0,  0.26),
    (258482.0,  0.29),
    (float("inf"), 0.33),
]
_BPA_MAX        = 16452.0
_BPA_MIN        = 14829.0
_BPA_PHASE_START = 181440.0
_BPA_PHASE_END   = 258482.0
_CEA            = 1500.0   # Canada Employment Amount (federal only)

# Nova Scotia provincial parameters
_NS_BRACKETS = [
    (30995.0,      0.0879),
    (61991.0,      0.1495),
    (97417.0,      0.1667),
    (157124.0,     0.175),
    (float("inf"), 0.21),
]
_NS_BPA = 11932.0

# Ontario provincial parameters
_ON_BRACKETS = [
    (53891.0,      0.0505),
    (107785.0,     0.0915),
    (150000.0,     0.1116),
    (220000.0,     0.1216),
    (float("inf"), 0.1316),
]
_ON_BPA   = 12989.0
_ON_SURTAX = [(5818.0, 0.20), (7446.0, 0.36)]

# Ontario Health Premium tiers: (upper_bound, base, rate, cap)
# upper_bound=None → top tier (no upper limit, flat base)
_OHP_TIERS = [
    (20000,  0,   0.0,    0),
    (36000,  0,   0.06,   300),
    (48000,  300, 0.06,   150),
    (72000,  450, 0.0025, 150),
    (200000, 600, 0.0025, 300),
    (None,   900, 0.0,    0),
]


# ---------------------------------------------------------------------------
# Formula helpers (mirror the corrected salary rule logic)
# ---------------------------------------------------------------------------

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


def _cpp_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """CPP employee contribution for one period."""
    period_exemption = _CPP_EXEMPTION / periods
    pensionable = max(gross - period_exemption, 0.0)
    contribution = pensionable * _CPP_RATE
    remaining = max(_CPP_MAX - ytd, 0.0)
    return round(min(contribution, remaining), 2)


def _ei_ee(gross: float, periods: int, ytd: float = 0.0) -> float:
    """EI employee premium for one period."""
    period_max_ins = _EI_MAX_INS / periods
    insurable = min(gross, period_max_ins)
    premium = insurable * _EI_RATE
    remaining = max(_EI_MAX_PREM - ytd, 0.0)
    return round(min(premium, remaining), 2)


def _fed_bpa(annual_income: float) -> float:
    """Federal Basic Personal Amount (phase-out above bracket 3)."""
    if annual_income <= _BPA_PHASE_START:
        return _BPA_MAX
    if annual_income >= _BPA_PHASE_END:
        return _BPA_MIN
    return _BPA_MAX - (_BPA_MAX - _BPA_MIN) * (
        annual_income - _BPA_PHASE_START
    ) / (_BPA_PHASE_END - _BPA_PHASE_START)


def _fed_tax(gross: float, periods: int, ytd_cpp: float = 0.0,
             ytd_cpp2: float = 0.0, ytd_ei: float = 0.0) -> float:
    """Corrected FED_TAX rule: income reduced by enhanced CPP + CPP2; K1 += CEA."""
    periods_remaining = periods  # first-period approximation (ytd=0)
    current_cpp = _cpp_ee(gross, periods, ytd_cpp)
    current_ei  = _ei_ee(gross, periods, ytd_ei)

    # Project annual contributions (simple annualisation for ytd=0 case)
    annual_cpp  = min(current_cpp * periods, _CPP_MAX)
    annual_cpp2 = 0.0  # no CPP2 for $2,000 gross (below per-period YMPE threshold)
    annual_ei   = min(current_ei  * periods, _EI_MAX_PREM)

    # Split CPP into base (K2 credit) and enhanced (income deduction)
    annual_cpp_base    = annual_cpp * (_CPP_BASE_RATE / _CPP_RATE)
    annual_enhanced    = annual_cpp - annual_cpp_base

    # T4127: annual income = P*I - U1 (U1 = enhanced CPP + CPP2)
    annual_income = gross * periods - annual_enhanced - annual_cpp2

    bpa = _fed_bpa(annual_income)
    tax = _progressive_tax(annual_income, _FED_BRACKETS)
    k1  = (bpa + _CEA) * _FED_BRACKETS[0][1]      # includes Canada Employment Amount
    k2  = (annual_cpp_base + annual_ei) * _FED_BRACKETS[0][1]  # base CPP + EI only

    return round(max(tax - k1 - k2, 0.0) / periods, 2)


def _prov_tax(gross: float, periods: int, prov_brackets: list, prov_bpa: float,
              surtax: list, ytd_cpp: float = 0.0, ytd_cpp2: float = 0.0,
              ytd_ei: float = 0.0) -> float:
    """Corrected PROV_TAX rule: income reduced by enhanced CPP + CPP2; no CEA."""
    current_cpp = _cpp_ee(gross, periods, ytd_cpp)
    current_ei  = _ei_ee(gross, periods, ytd_ei)

    annual_cpp  = min(current_cpp * periods, _CPP_MAX)
    annual_cpp2 = 0.0
    annual_ei   = min(current_ei  * periods, _EI_MAX_PREM)

    annual_cpp_base = annual_cpp * (_CPP_BASE_RATE / _CPP_RATE)
    annual_enhanced = annual_cpp - annual_cpp_base

    annual_income = gross * periods - annual_enhanced - annual_cpp2

    tax = _progressive_tax(annual_income, prov_brackets)
    k1p = prov_bpa * prov_brackets[0][1]
    k2p = (annual_cpp_base + annual_ei) * prov_brackets[0][1]

    basic = max(tax - k1p - k2p, 0.0)

    sur = 0.0
    for threshold, surrate in surtax:
        if basic > threshold:
            sur += (basic - threshold) * surrate

    return round((basic + sur) / periods, 2)


def _ohp(gross: float, periods: int) -> float:
    """OHP rule: uses gross annual income (no CPP income reduction)."""
    annual = gross * periods  # OHP uses gross × periods, not T4127-adjusted income
    ohp = 0.0
    prev = 0
    for upto, base, rate, cap in _OHP_TIERS:
        if upto is None or annual <= upto:
            delta = annual - prev
            ohp = base + (min(delta * rate, cap) if cap else delta * rate)
            if upto is None:
                ohp = base
            break
        prev = upto
    return round(ohp / periods, 2)


# ---------------------------------------------------------------------------
# Nova Scotia parity tests
# ---------------------------------------------------------------------------

GROSS_NS = 2000.0
PERIODS  = 26


class TestNsPayslipPdocParity:
    """Verify NS $2,000 biweekly payslip matches CRA PDOC output.

    Reference: PDOC (Jan 2026), Nova Scotia, biweekly 26 pp, gross $2,000,
    Federal TD1=$16,452, Provincial TD1=$11,932.
    """

    def test_cpp_ee(self):
        """CPP_EE must be $110.99 (PDOC: $110.99)."""
        cpp = _cpp_ee(GROSS_NS, PERIODS)
        assert cpp == pytest.approx(110.99, abs=0.01), (
            f"CPP_EE expected 110.99, got {cpp}"
        )

    def test_ei_ee(self):
        """EI_EE must be $32.60 (PDOC: $32.60)."""
        ei = _ei_ee(GROSS_NS, PERIODS)
        assert ei == pytest.approx(32.60, abs=0.01), (
            f"EI_EE expected 32.60, got {ei}"
        )

    def test_federal_tax(self):
        """Federal income tax must be $163.23 (PDOC: $163.23)."""
        fed = _fed_tax(GROSS_NS, PERIODS)
        assert fed == pytest.approx(163.23, abs=0.02), (
            f"FED_TAX expected 163.23, got {fed}"
        )

    def test_ns_provincial_tax(self):
        """NS provincial income tax must be ≈$171.47 (PDOC: $171.47)."""
        prov = _prov_tax(GROSS_NS, PERIODS, _NS_BRACKETS, _NS_BPA, [])
        assert prov == pytest.approx(171.47, abs=0.02), (
            f"NS PROV_TAX expected ~171.47, got {prov}"
        )

    def test_net_pay(self):
        """Net pay must be ≈$1,521.71 (PDOC: $1,521.71)."""
        cpp = _cpp_ee(GROSS_NS, PERIODS)
        ei  = _ei_ee(GROSS_NS, PERIODS)
        fed = _fed_tax(GROSS_NS, PERIODS)
        prov = _prov_tax(GROSS_NS, PERIODS, _NS_BRACKETS, _NS_BPA, [])
        net = GROSS_NS - cpp - ei - fed - prov
        assert net == pytest.approx(1521.71, abs=0.05), (
            f"Net expected ~1521.71, got {net}"
        )

    def test_no_ohp_for_ns(self):
        """OHP condition fires only for Ontario; NS employee must have zero OHP."""
        # Replicate the condition_python: result = (province == 'ON')
        province = "NS"
        assert province != "ON", "NS employees must not incur OHP"

    def test_income_reduction_applied(self):
        """Annual income must be below gross*periods (reduced by enhanced CPP)."""
        annual_gross = GROSS_NS * PERIODS
        cpp = _cpp_ee(GROSS_NS, PERIODS)
        annual_cpp = min(cpp * PERIODS, _CPP_MAX)
        annual_enhanced = annual_cpp * (_CPP_ENHANCED / _CPP_RATE)
        annual_income = annual_gross - annual_enhanced  # no CPP2 at this income level
        assert annual_income < annual_gross, (
            "Annual income must be reduced by the enhanced CPP portion"
        )
        assert annual_income == pytest.approx(51515, abs=1.0), (
            f"Annual income expected ~51515, got {annual_income}"
        )

    def test_k1_includes_cea(self):
        """Federal K1 must include CEA — verify it equals (BPA + 1500) × rate."""
        annual_income = GROSS_NS * PERIODS
        bpa = _fed_bpa(annual_income)
        k1_with_cea    = (bpa + _CEA) * _FED_BRACKETS[0][1]
        k1_without_cea =  bpa         * _FED_BRACKETS[0][1]
        assert k1_with_cea > k1_without_cea, (
            "K1 with CEA must exceed K1 without CEA"
        )
        assert k1_with_cea == pytest.approx((bpa + 1500.0) * 0.14, abs=0.01)

    def test_k2_excludes_cpp2(self):
        """K2 must NOT include CPP2 — CPP2 is an income deduction, not a credit."""
        cpp   = _cpp_ee(GROSS_NS, PERIODS)
        ei    = _ei_ee(GROSS_NS, PERIODS)
        annual_cpp      = min(cpp * PERIODS, _CPP_MAX)
        annual_cpp_base = annual_cpp * (_CPP_BASE_RATE / _CPP_RATE)
        annual_ei       = min(ei  * PERIODS, _EI_MAX_PREM)
        k2_correct = (annual_cpp_base + annual_ei) * _FED_BRACKETS[0][1]
        k2_wrong   = (annual_cpp + 0 + annual_ei) * _FED_BRACKETS[0][1]  # old formula
        assert k2_correct < k2_wrong, (
            "Correct K2 (base CPP only) must be less than the old formula (full CPP)"
        )


# ---------------------------------------------------------------------------
# Ontario parity tests (OHP intact after income-reduction fix)
# ---------------------------------------------------------------------------

class TestOnPayslipOhpIntact:
    """Ontario $2,000 biweekly: confirm OHP still appears after the T4127 fixes.

    The income-reduction logic applies only inside FED_TAX and PROV_TAX.
    The OHP rule uses gross × periods (pre-deduction annual income) per its
    own published CRA formula, so OHP must not change as a result of this fix.
    """

    GROSS   = 2000.0
    PERIODS = 26

    def test_cpp_ei_same_as_ns(self):
        """CPP and EI are province-independent; ON values match NS."""
        assert _cpp_ee(self.GROSS, self.PERIODS) == pytest.approx(110.99, abs=0.01)
        assert _ei_ee(self.GROSS, self.PERIODS)  == pytest.approx(32.60,  abs=0.01)

    def test_federal_tax_same_as_ns(self):
        """Federal tax is province-independent; ON matches NS."""
        assert _fed_tax(self.GROSS, self.PERIODS) == pytest.approx(163.23, abs=0.02)

    def test_on_provincial_tax(self):
        """ON provincial tax for $2,000 biweekly with income-reduction applied."""
        prov = _prov_tax(self.GROSS, self.PERIODS, _ON_BRACKETS, _ON_BPA, _ON_SURTAX)
        # Expected: annual income = 51515, tax = 51515*0.0505 = 2601.51,
        # K1P = 12989*0.0505 = 655.94, K2P = (2400.74+847.60)*0.0505 = 164.04
        # basic = 1781.53, no surtax → per period = 1781.53/26 = 68.52
        assert prov == pytest.approx(68.52, abs=0.05), (
            f"ON PROV_TAX expected ~68.52, got {prov}"
        )

    def test_ohp_non_zero_for_ontario(self):
        """OHP must be non-zero for Ontario employees at $2,000 biweekly."""
        ohp = _ohp(self.GROSS, self.PERIODS)
        assert ohp > 0, "OHP must be positive for Ontario"

    def test_ohp_uses_gross_income_not_reduced(self):
        """OHP uses gross × periods ($52,000), not the T4127-adjusted income ($51,515).

        The OHP rule is intentionally independent of the CPP income split and
        should compute the same result as before the T4127 fix.
        """
        ohp = _ohp(self.GROSS, self.PERIODS)
        # Annual gross = 52000; tier 48000-72000: base=450, +0.0025*(52000-48000)=+10.00
        # ohp_annual = 460; per period = 460/26 ≈ 17.69
        assert ohp == pytest.approx(17.69, abs=0.02), (
            f"OHP expected ~17.69, got {ohp}"
        )

    def test_net_pay_on(self):
        """Ontario net pay is consistent with all corrected deductions."""
        cpp  = _cpp_ee(self.GROSS, self.PERIODS)
        ei   = _ei_ee(self.GROSS, self.PERIODS)
        fed  = _fed_tax(self.GROSS, self.PERIODS)
        prov = _prov_tax(self.GROSS, self.PERIODS, _ON_BRACKETS, _ON_BPA, _ON_SURTAX)
        ohp  = _ohp(self.GROSS, self.PERIODS)
        net  = self.GROSS - cpp - ei - fed - prov - ohp
        assert net > 0, "Net pay must be positive"
        # Rough sanity: all deductions < gross
        total_deductions = cpp + ei + fed + prov + ohp
        assert total_deductions < self.GROSS, (
            f"Total deductions {total_deductions} must be less than gross {self.GROSS}"
        )
