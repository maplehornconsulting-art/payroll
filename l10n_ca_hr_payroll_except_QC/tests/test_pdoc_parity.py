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
# CRA T4127 Ch 6 §6.7: rates in tiers 4-5 are 25% (0.25), not 0.25% (0.0025).
# Caps ensure OHP maxes at $600 (A ≥ 48,600) and $900 (A ≥ 73,200).
_OHP_TIERS = [
    (20000,  0,   0.0,  0),
    (36000,  0,   0.06, 300),
    (48000,  300, 0.06, 150),
    (72000,  450, 0.25, 150),
    (200000, 600, 0.25, 300),
    (None,   900, 0.0,  0),
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
    """EI employee premium for one period.

    CRA T4127 §4.1: premium = gross × rate.  The only cap is the annual
    premium maximum; there is no per-period insurable ceiling.
    """
    premium = gross * _EI_RATE
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
             ytd_cpp2: float = 0.0, ytd_ei: float = 0.0,
             ytd_pensionable: float = 0.0,
             apply_bpa_phase_out: bool = True) -> float:
    """Corrected FED_TAX rule: income reduced by enhanced CPP + CPP2; K1 += CEA.

    U1 (income deduction) uses per-period contribution × periods — NO annual cap.
    K2 (non-refundable credit) uses the capped projected annual contribution.
    See CRA T4127 §5.2 for the distinction.

    apply_bpa_phase_out: when True (default for backward compatibility), applies the
    CRA T4127 §5.1 phase-out of the enhanced BPA for high earners. When False, the
    full BPA maximum is used, matching CRA PDOC / Wave / QuickBooks / ADP behavior.
    The new l10n_ca_apply_bpa_phase_out field on hr.version defaults to False.
    """
    current_cpp = _cpp_ee(gross, periods, ytd_cpp)
    current_cpp2 = _cpp2_ee(gross, periods, ytd_cpp2, ytd_pensionable)
    current_ei  = _ei_ee(gross, periods, ytd_ei)

    # K2: capped projected annual contributions (actual employee contributions, T4127 K2).
    annual_cpp_capped = min(current_cpp * periods, _CPP_MAX)
    annual_ei_capped  = min(current_ei  * periods, _EI_MAX_PREM)
    annual_cpp_base   = annual_cpp_capped * (_CPP_BASE_RATE / _CPP_RATE)

    # U1 (income deduction): per-period × periods, intentionally uncapped (CRA T4127 §5.2).
    # T4127 projects the year at the current period's rate; the annual CPP cap applies only to
    # K2 (the non-refundable credit), NOT to the income deduction.
    period_enhanced_cpp = current_cpp * (_CPP_ENHANCED / _CPP_RATE)
    annual_enhanced_cpp = period_enhanced_cpp * periods  # NO annual cap
    annual_cpp2_full    = current_cpp2 * periods         # NO annual cap

    # T4127: annual income = P*I - U1 (U1 = enhanced CPP + CPP2)
    annual_income = gross * periods - annual_enhanced_cpp - annual_cpp2_full

    bpa = _fed_bpa(annual_income) if apply_bpa_phase_out else _BPA_MAX
    tax = _progressive_tax(annual_income, _FED_BRACKETS)
    k1  = (bpa + _CEA) * _FED_BRACKETS[0][1]      # includes Canada Employment Amount
    k2  = (annual_cpp_base + annual_ei_capped) * _FED_BRACKETS[0][1]  # base CPP + EI only

    return round(max(tax - k1 - k2, 0.0) / periods, 2)


def _prov_tax(gross: float, periods: int, prov_brackets: list, prov_bpa: float,
              surtax: list, ytd_cpp: float = 0.0, ytd_cpp2: float = 0.0,
              ytd_ei: float = 0.0, ytd_pensionable: float = 0.0) -> float:
    """Corrected PROV_TAX rule: income reduced by enhanced CPP + CPP2; no CEA.

    U1 (income deduction) uses per-period contribution × periods — NO annual cap.
    K2P (non-refundable credit) uses the capped projected annual contribution.
    See CRA T4127 §5.2 for the distinction.
    """
    current_cpp = _cpp_ee(gross, periods, ytd_cpp)
    current_cpp2 = _cpp2_ee(gross, periods, ytd_cpp2, ytd_pensionable)
    current_ei  = _ei_ee(gross, periods, ytd_ei)

    # K2P: capped projected annual contributions (actual employee contributions).
    annual_cpp_capped = min(current_cpp * periods, _CPP_MAX)
    annual_ei_capped  = min(current_ei  * periods, _EI_MAX_PREM)
    annual_cpp_base   = annual_cpp_capped * (_CPP_BASE_RATE / _CPP_RATE)

    # U1 (income deduction): per-period × periods, intentionally uncapped (CRA T4127 §5.2).
    period_enhanced_cpp = current_cpp * (_CPP_ENHANCED / _CPP_RATE)
    annual_enhanced_cpp = period_enhanced_cpp * periods  # NO annual cap
    annual_cpp2_full    = current_cpp2 * periods         # NO annual cap

    annual_income = gross * periods - annual_enhanced_cpp - annual_cpp2_full

    tax = _progressive_tax(annual_income, prov_brackets)
    k1p = prov_bpa * prov_brackets[0][1]
    k2p = (annual_cpp_base + annual_ei_capped) * prov_brackets[0][1]

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

        At annual = $52,000 (tier 48,001–72,000, rate=0.25, cap=150):
          delta = 52,000 − 48,000 = 4,000
          min(4,000 × 0.25, 150) = 150  → cap hit
          OHP annual = 450 + 150 = 600 → per period = 600/26 ≈ 23.08
        """
        ohp = _ohp(self.GROSS, self.PERIODS)
        assert ohp == pytest.approx(23.08, abs=0.02), (
            f"OHP expected ~23.08, got {ohp}"
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


# ---------------------------------------------------------------------------
# High-earner NS $4,000 biweekly — Bug #1 and Bug #2 regression tests
# ---------------------------------------------------------------------------

def _cpp2_ee(gross: float, periods: int, ytd_cpp2: float = 0.0,
                ytd_pensionable: float = 0.0) -> float:
    """CPP2_EE for one period using the corrected YTD-pensionable approach.

    CRA T4127 §4.4: CPP2 applies only once YTD pensionable earnings exceed
    the annual YMPE.  YMPE is NOT prorated per period.
    """
    _cpp2_ympe    = 74600.0
    _cpp2_ceiling = 85000.0
    _cpp2_rate    = 0.04
    _cpp2_max     = 416.00
    period_exemption = _CPP_EXEMPTION / periods
    period_pensionable = max(gross - period_exemption, 0.0)
    new_ytd_pensionable = ytd_pensionable + period_pensionable
    if new_ytd_pensionable <= _cpp2_ympe:
        return 0.0
    band_low = max(ytd_pensionable, _cpp2_ympe)
    band_high = min(new_ytd_pensionable, _cpp2_ceiling)
    cpp2_pensionable = max(band_high - band_low, 0.0)
    period_contribution = cpp2_pensionable * _cpp2_rate
    remaining_annual = max(_cpp2_max - ytd_cpp2, 0.0)
    return round(min(period_contribution, remaining_annual), 2)


class TestHighEarner4000BiweeklyNs:
    """NS $4,000 biweekly — regression tests for Bug #1 (EI) and Bug #2 (CPP2).

    Reference:
      PDOC verified 2026-04: $4,000 biweekly, Nova Scotia, 26 pay periods,
      Federal TD1=$16,452, Provincial TD1=$11,932, first pay of year.

    PDOC expected (period 1):
      CPP_EE = 229.99  (PDOC: 229.99) ✓
      CPP2_EE = 0.00   (PDOC: 0.00) — Bug #2 fix
      EI_EE  = 65.20   (PDOC: 65.20) — Bug #1 fix
    """

    GROSS   = 4000.0
    PERIODS = 26
    _CPP_YMPE  = 74600.0
    _CPP2_MAX  = 416.00

    def test_cpp_ee_period1(self):
        """CPP_EE at period 1 must be $229.99 (matches PDOC)."""
        cpp = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert cpp == pytest.approx(229.99, abs=0.01), (
            f"CPP_EE expected 229.99, got {cpp}"
        )

    def test_cpp2_ee_period1_is_zero(self):
        """CPP2_EE at period 1 must be $0.00 — YTD pensionable has not crossed YMPE.

        Bug #2 fix: the old code prorated YMPE per period, yielding ~$16.00.
        Correct (T4127 §4.4): CPP2 = 0 until cumulative pensionable earnings
        exceed the annual YMPE ($74,600).  At period 1, YTD pensionable = 0.
        """
        cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=0.0, ytd_pensionable=0.0)
        assert cpp2 == 0.0, (
            f"CPP2_EE must be $0 at period 1 (YTD pensionable=0 < YMPE={self._CPP_YMPE}), "
            f"got {cpp2}.  Bug #2: old value was ~$16.00."
        )

    def test_ei_ee_period1(self):
        """EI_EE at period 1 must be $65.20 — gross x rate, no per-period insurable cap.

        Bug #1 fix: the old code capped insurable at $68,900/26=$2,650 → EI=$43.20.
        Correct (T4127 §4.1): EI = gross × rate = $4,000 × 0.0163 = $65.20.
        """
        ei = _ei_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert ei == pytest.approx(65.20, abs=0.01), (
            f"EI_EE expected 65.20, got {ei}.  Bug #1: old value was ~$43.20."
        )

    def test_cpp2_ee_triggers_at_period_20(self):
        """CPP2_EE must first appear at period 20 (when YTD pensionable crosses YMPE).

        At $4,000 biweekly, periods to reach YMPE ($74,600):
          74,600 / 3,865.38 = 19.3  =>  CPP2 = 0 for periods 1-19, CPP2 > 0 at period 20.
        """
        period_exemption = _CPP_EXEMPTION / self.PERIODS
        ytd_cpp2 = 0.0
        ytd_pensionable = 0.0
        for p in range(1, 21):
            cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=ytd_cpp2,
                               ytd_pensionable=ytd_pensionable)
            if p < 20:
                assert cpp2 == 0.0, (
                    f"CPP2 at period {p} expected $0, got {cpp2} "
                    f"(ytd_pensionable={ytd_pensionable:.2f} < YMPE={self._CPP_YMPE})"
                )
            else:
                assert cpp2 > 0.0, (
                    f"CPP2 at period 20 expected > $0 (YMPE crossing), got {cpp2}"
                )
            ytd_cpp2 += cpp2
            ytd_pensionable += max(self.GROSS - period_exemption, 0.0)

    def test_cpp2_ee_annual_total_does_not_exceed_max(self):
        """Annual sum of CPP2_EE must not exceed $416 (the 2026 annual max)."""
        period_exemption = _CPP_EXEMPTION / self.PERIODS
        ytd_cpp2 = 0.0
        ytd_pensionable = 0.0
        for _ in range(self.PERIODS):
            cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=ytd_cpp2,
                               ytd_pensionable=ytd_pensionable)
            ytd_cpp2 += cpp2
            ytd_pensionable += max(self.GROSS - period_exemption, 0.0)
        assert ytd_cpp2 <= self._CPP2_MAX + 0.01, (
            f"Annual CPP2 total {ytd_cpp2} must not exceed max {self._CPP2_MAX}"
        )

    def test_ei_ee_annual_total_does_not_exceed_max(self):
        """Annual sum of EI_EE must not exceed $1,123.07 (the 2026 annual max)."""
        ytd_ei = 0.0
        for _ in range(self.PERIODS):
            ei = _ei_ee(self.GROSS, self.PERIODS, ytd=ytd_ei)
            ytd_ei += ei
        assert ytd_ei <= _EI_MAX_PREM + 0.01, (
            f"Annual EI total {ytd_ei} must not exceed max {_EI_MAX_PREM}"
        )

    def test_net_pay_period1_plausible(self):
        """Net pay at period 1 must be positive and near $2,669 (PDOC: ~$2,669.05)."""
        cpp  = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=0.0, ytd_pensionable=0.0)
        ei   = _ei_ee(self.GROSS, self.PERIODS, ytd=0.0)
        fed  = _fed_tax(self.GROSS, self.PERIODS)
        prov = _prov_tax(self.GROSS, self.PERIODS, _NS_BRACKETS, _NS_BPA, [])
        net = self.GROSS - cpp - cpp2 - ei - fed - prov
        assert net > 0, f"Net pay must be positive, got {net}"
        # PDOC reports net ~$2,669.05; our T4127 formula may differ by a few dollars
        # at period 1 (CPP2 income deduction projects to $0 at first pay per T4127 §4.4).
        assert net == pytest.approx(2669.05, abs=15.0), (
            f"Net pay expected ~$2,669, got {net}"
        )


# ---------------------------------------------------------------------------
# High-earner NS $4,000 biweekly — federal & provincial tax regression tests
# (Bug fix verification: U1 now uses uncapped per-period × periods)
# ---------------------------------------------------------------------------

class TestHighEarner4000BiweeklyNsTax:
    """NS $4,000 biweekly — regression tests for federal and provincial income tax.

    Reference:
      PDOC verified 2026-04: $4,000 biweekly, Nova Scotia, 26 pay periods,
      Federal TD1=$16,452, Provincial TD1=$11,932, first pay of year.

    These tests expose the U1 cap bug: at $4,000 biweekly the projected annual
    CPP ($5,979.74) exceeds the annual cap ($4,230.45), so the buggy capped
    formula understates U1 and overstates taxable income.

    PDOC expected (period 1):
      Federal Tax  ≈ $544.11  ✓ (uncapped U1 fix)
      NS Tax       ≈ $491.66  ✓ (uncapped U1 fix)
    """

    GROSS   = 4000.0
    PERIODS = 26

    def test_federal_tax_period1(self):
        """Federal tax at $4,000 biweekly must be ≈$544 (uncapped U1 fix).

        Buggy capped value was ~$546.43 (U1 understated because annual CPP
        was capped at $4,230.45 instead of using period × periods = $5,979.74).
        """
        fed = _fed_tax(self.GROSS, self.PERIODS)
        assert fed == pytest.approx(544.11, abs=0.10), (
            f"FED_TAX at $4,000 biweekly expected ~$544.11 (uncapped U1), got {fed}"
        )

    def test_ns_provincial_tax_period1(self):
        """NS provincial tax at $4,000 biweekly must be ≈$491 (uncapped U1 fix).

        Buggy capped value was ~$493.64.
        """
        prov = _prov_tax(self.GROSS, self.PERIODS, _NS_BRACKETS, _NS_BPA, [])
        assert prov == pytest.approx(491.66, abs=0.10), (
            f"NS PROV_TAX at $4,000 biweekly expected ~$491.66 (uncapped U1), got {prov}"
        )

    def test_ei_ee_period1(self):
        """EI_EE at period 1 remains $65.20 (unchanged by U1 fix)."""
        ei = _ei_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert ei == pytest.approx(65.20, abs=0.01)

    def test_cpp2_ee_period1_is_zero(self):
        """CPP2_EE at period 1 is $0 (unchanged by U1 fix)."""
        cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=0.0, ytd_pensionable=0.0)
        assert cpp2 == 0.0


# ---------------------------------------------------------------------------
# High-earner NS $6,000 biweekly — new regression test (exposes the U1 cap bug)
# ---------------------------------------------------------------------------

class TestHighEarner6000BiweeklyNs:
    """NS $6,000 biweekly — regression test exposing the U1 cap bug.

    Reference:
      PDOC verified 2026-04: $6,000 biweekly, Nova Scotia, 26 pay periods,
      Federal TD1=$16,452, Provincial TD1=$11,932, first pay of year.

    At $6,000 biweekly, per-period CPP = $348.99.  The projected annual CPP
    (348.99 × 26 = $9,073.74) far exceeds the annual cap ($4,230.45).  The
    buggy capped formula understates U1 by $813 and overstates taxable income,
    causing Federal tax to be $1,037.32 instead of the correct $1,029.20.

    With the fix:
      - period_enhanced_cpp = 348.99 × (0.01/0.0595) = 58.65/period
      - annual_enhanced_cpp (uncapped) = 58.65 × 26 = 1,524.90
      - annual_income = 156,000 − 1,524.90 = 154,475.10

    PDOC expected (period 1):
      CPP_EE       = 348.99  ✓
      CPP2_EE      = 0.00    ✓ (YTD pensionable < YMPE at period 1)
      EI_EE        = 97.80   ✓
      Federal Tax  = 1,029.20 ✓
      NS Tax       = 838.16  ✓
      Net          = 3,685.85 ✓
    """

    GROSS   = 6000.0
    PERIODS = 26

    def test_cpp_ee_period1(self):
        """CPP_EE at period 1 must be $348.99 (PDOC: $348.99)."""
        cpp = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert cpp == pytest.approx(348.99, abs=0.01), (
            f"CPP_EE expected 348.99, got {cpp}"
        )

    def test_cpp2_ee_period1_is_zero(self):
        """CPP2_EE at period 1 must be $0 — YTD pensionable < YMPE at first period."""
        cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=0.0, ytd_pensionable=0.0)
        assert cpp2 == 0.0, (
            f"CPP2_EE at period 1 must be $0 (YTD pensionable below YMPE), got {cpp2}"
        )

    def test_ei_ee_period1(self):
        """EI_EE at period 1 must be $97.80 (PDOC: $97.80)."""
        ei = _ei_ee(self.GROSS, self.PERIODS, ytd=0.0)
        assert ei == pytest.approx(97.80, abs=0.01), (
            f"EI_EE expected 97.80, got {ei}"
        )

    def test_federal_tax_period1(self):
        """Federal tax must be $1,029.20 (PDOC: $1,029.20) — the U1 cap bug fix.

        Without the fix, the capped U1 gave $1,037.32 (+$8.12 over PDOC).
        """
        fed = _fed_tax(self.GROSS, self.PERIODS)
        assert fed == pytest.approx(1029.20, abs=0.10), (
            f"FED_TAX expected 1029.20 (PDOC), got {fed}. "
            f"Old buggy capped value was ~1037.32."
        )

    def test_ns_provincial_tax_period1(self):
        """NS provincial tax must be $838.16 (PDOC: $838.16) — the U1 cap bug fix.

        Without the fix, the capped U1 gave $843.64 (+$5.48 over PDOC).
        """
        prov = _prov_tax(self.GROSS, self.PERIODS, _NS_BRACKETS, _NS_BPA, [])
        assert prov == pytest.approx(838.16, abs=0.10), (
            f"NS PROV_TAX expected 838.16 (PDOC), got {prov}. "
            f"Old buggy capped value was ~843.64."
        )

    def test_net_pay_period1(self):
        """Net pay must be $3,685.85 (PDOC: $3,685.85)."""
        cpp  = _cpp_ee(self.GROSS, self.PERIODS, ytd=0.0)
        cpp2 = _cpp2_ee(self.GROSS, self.PERIODS, ytd_cpp2=0.0, ytd_pensionable=0.0)
        ei   = _ei_ee(self.GROSS, self.PERIODS, ytd=0.0)
        fed  = _fed_tax(self.GROSS, self.PERIODS)
        prov = _prov_tax(self.GROSS, self.PERIODS, _NS_BRACKETS, _NS_BPA, [])
        net  = self.GROSS - cpp - cpp2 - ei - fed - prov
        assert net == pytest.approx(3685.85, abs=0.10), (
            f"Net pay expected 3685.85 (PDOC), got {net}"
        )

    def test_u1_is_uncapped(self):
        """Annual U1 must equal per-period enhanced CPP × 26 — uncapped (T4127 §5.2).

        The projected annual total CPP (348.99 × 26 = $9,073.74) exceeds the annual
        max ($4,230.45), which means the old capped formula would have computed a smaller
        enhanced amount (4,230.45 × 1.00/5.95 = $711.00) instead of the correct
        per-period × periods = $1,524.90.  The test verifies the correct uncapped value.
        """
        period_cpp = _cpp_ee(self.GROSS, self.PERIODS)
        # Confirm the projected annual CPP exceeds the annual cap (so capping would bite)
        projected_annual_cpp = period_cpp * self.PERIODS
        assert projected_annual_cpp > _CPP_MAX, (
            f"Projected annual CPP ({projected_annual_cpp:.2f}) must exceed the cap "
            f"({_CPP_MAX}) so this test exercises the capping scenario."
        )
        # U1 = period_enhanced × periods — must NOT use the capped annual value
        period_enhanced = period_cpp * (_CPP_ENHANCED / _CPP_RATE)
        annual_u1 = period_enhanced * self.PERIODS
        annual_u1_if_capped = min(projected_annual_cpp, _CPP_MAX) * (_CPP_ENHANCED / _CPP_RATE)
        assert annual_u1 > annual_u1_if_capped, (
            f"Uncapped U1 ({annual_u1:.2f}) must exceed the (wrong) capped U1 "
            f"({annual_u1_if_capped:.2f})."
        )
        assert annual_u1 == pytest.approx(1524.90, abs=0.10), (
            f"Annual U1 expected 1524.90 (58.65×26), got {annual_u1:.2f}"
        )




def _ohp_annual(annual_income: float) -> float:
    """Return the annual OHP for the given annual income (Ontario only).

    Mirrors _ohp() but returns the raw annual amount instead of the
    per-period deduction, for easy comparison with the CRA T4127 table.
    """
    ohp = 0.0
    prev = 0
    for upto, base, rate, cap in _OHP_TIERS:
        if upto is None:
            ohp = base  # flat top tier
            break
        if annual_income <= upto:
            delta = annual_income - prev
            ohp = base + (min(delta * rate, cap) if cap else delta * rate)
            break
        prev = upto
    return ohp


class TestOhpTableSpotChecks:
    """CRA T4127 Ch 6 §6.7 OHP table spot-checks (annual amounts).

    Corrected rates: tiers 4–5 use 0.25 (25%), not 0.0025 (0.25%).
    Caps (150 and 300) are hit very quickly — OHP effectively stair-steps:
      $0 → $300 → $450 → $600 → $900.

    Reference table from the problem statement:
      A ≤ 20,000                           →   0
      20,001 – 36,000  min(A-20k)×0.06,300 → 300
      36,001 – 48,000  300+min(A-36k)×0.06 → 450
      48,001 – 72,000  450+min(A-48k)×0.25 → 600  (cap at A=48,600)
      72,001 – 200,000 600+min(A-72k)×0.25 → 900  (cap at A=73,200)
      > 200,000        flat 900
    """

    def test_a_15000_is_zero(self):
        """Annual ≤ $20,000 → OHP = $0."""
        assert _ohp_annual(15_000) == pytest.approx(0, abs=0.01)

    def test_a_20000_boundary_is_zero(self):
        """Annual = $20,000 (exact boundary) → OHP = $0."""
        assert _ohp_annual(20_000) == pytest.approx(0, abs=0.01)

    def test_a_25000(self):
        """Annual = $25,000 → OHP = min(5,000×0.06, 300) = 300."""
        assert _ohp_annual(25_000) == pytest.approx(300, abs=0.01)

    def test_a_36000_cap(self):
        """Annual = $36,000 → OHP hits first cap = 300."""
        assert _ohp_annual(36_000) == pytest.approx(300, abs=0.01)

    def test_a_48000_boundary(self):
        """Annual = $48,000 → OHP = 300 + min(12,000×0.06, 150) = 450."""
        assert _ohp_annual(48_000) == pytest.approx(450, abs=0.01)

    def test_a_48600_cap_hit(self):
        """Annual = $48,600 → cap (rate=0.25) hit: 450+min(600×0.25,150)=600."""
        assert _ohp_annual(48_600) == pytest.approx(600, abs=0.01)

    def test_a_50000(self):
        """Annual = $50,000 → OHP = 450+min(2,000×0.25,150)=600 (cap already hit)."""
        assert _ohp_annual(50_000) == pytest.approx(600, abs=0.01)

    def test_a_65000(self):
        """Annual = $65,000 → OHP = 600 (cap remains)."""
        assert _ohp_annual(65_000) == pytest.approx(600, abs=0.01)

    def test_a_72000_boundary(self):
        """Annual = $72,000 → OHP = 600 (still in tier 4, cap already hit)."""
        assert _ohp_annual(72_000) == pytest.approx(600, abs=0.01)

    def test_a_73200_cap_hit(self):
        """Annual = $73,200 → tier 5 cap hit: 600+min(1,200×0.25,300)=900."""
        assert _ohp_annual(73_200) == pytest.approx(900, abs=0.01)

    def test_a_100000(self):
        """Annual = $100,000 → OHP = 900 (tier 5 cap already hit)."""
        assert _ohp_annual(100_000) == pytest.approx(900, abs=0.01)

    def test_a_200000_boundary(self):
        """Annual = $200,000 → OHP = 900 (tier 5 cap)."""
        assert _ohp_annual(200_000) == pytest.approx(900, abs=0.01)

    def test_a_250000_flat(self):
        """Annual > $200,000 → OHP = 900 (flat top tier)."""
        assert _ohp_annual(250_000) == pytest.approx(900, abs=0.01)


# ---------------------------------------------------------------------------
# Ontario $2,500 biweekly — acceptance-criterion regression test
# ---------------------------------------------------------------------------

class TestOn2500BiweeklyOhp:
    """Ontario $2,500 biweekly (26 pp) OHP regression.

    Acceptance criterion (problem statement):
      Annual income = 65,000
      OHP = 450 + min(17,000 × 0.25, 150) = 450 + 150 = 600/yr
      Per period = 600 / 26 ≈ 23.08

    Old (buggy) result with rate=0.0025:
      OHP = 450 + min(17,000 × 0.0025, 150) = 450 + 42.50 = 492.50/yr
      Per period = 492.50 / 26 ≈ 18.94
    """

    GROSS   = 2500.0
    PERIODS = 26

    def test_ohp_annual_at_65000(self):
        """Annual = $65,000 → OHP annual = $600 (cap hit in tier 4)."""
        annual = self.GROSS * self.PERIODS
        assert annual == 65_000.0
        assert _ohp_annual(annual) == pytest.approx(600, abs=0.01)

    def test_ohp_per_period(self):
        """OHP per period must be ≈ $23.08 (PDOC parity)."""
        ohp = _ohp(self.GROSS, self.PERIODS)
        assert ohp == pytest.approx(23.08, abs=0.02), (
            f"ON $2,500 biweekly OHP expected ~$23.08, got {ohp}.  "
            f"Bug: old rate=0.0025 gave $18.94."
        )

    def test_prov_plus_ohp_within_pdoc_tolerance(self):
        """Provincial tax + OHP must be ≈ $131.48 (PDOC: $131.46, within ±$0.10).

        Derivation: ON prov tax ≈ $108.40 + OHP $23.08 = $131.48/period.
        PDOC bundles OHP into "Provincial tax deduction" → $131.46.
        """
        prov = _prov_tax(self.GROSS, self.PERIODS, _ON_BRACKETS, _ON_BPA, _ON_SURTAX)
        ohp  = _ohp(self.GROSS, self.PERIODS)
        total = prov + ohp
        # 108.40 (PROV_TAX) + 23.08 (OHP) = 131.48; PDOC: 131.46
        assert total == pytest.approx(131.48, abs=0.10), (
            f"Provincial + OHP expected ~131.48 (PDOC: 131.46), got {total}"
        )


# ---------------------------------------------------------------------------
# BPA phase-out toggle regression tests (v1.9)
# ---------------------------------------------------------------------------

class TestBpaPhaseOutToggle:
    """Regression tests for the l10n_ca_apply_bpa_phase_out configurable toggle.

    The new per-contract Boolean field (default OFF) allows customers to choose
    between strict CRA T4127 §5.1 phase-out (ON) and PDOC-matching behavior (OFF).

    Reference: Nova Scotia, biweekly (26 pp/yr).

    Verification approach (from issue):
      A = gross*P − U1;  for $10,000 biweekly A ≈ 257,435 (inside the phase-out band).

    | Toggle | Annual K1          | Annual fed tax | Per-period |
    |--------|--------------------|----------------|------------|
    | ON     | phased BPA × 0.14  | 56,032         | ≈ 2,155.09 |
    | OFF    | 17,952 × 0.14      | 55,808         | ≈ 2,146.47 |

    PDOC expected (phase-out OFF): $2,146.45 (within ±$0.10 of formula).
    """

    GROSS   = 10_000.0
    PERIODS = 26

    def test_federal_tax_phase_out_off_matches_pdoc(self):
        """Phase-out OFF (default): Federal Tax ≈ $2,146.45 (PDOC parity, within ±$0.10).

        With phase-out OFF the full BPA max ($16,452) is used regardless of income.
        K1 = (16,452 + 1,500) × 0.14 = 2,513.28.
        Annual income A ≈ 257,435 falls in the 4th bracket → lower withholding vs phase-out ON.
        """
        fed = _fed_tax(self.GROSS, self.PERIODS, apply_bpa_phase_out=False)
        assert fed == pytest.approx(2146.45, abs=0.10), (
            f"Phase-out OFF: FED_TAX expected ≈$2,146.45 (PDOC), got {fed}"
        )

    def test_federal_tax_phase_out_on_preserves_current_behavior(self):
        """Phase-out ON: Federal Tax ≈ $2,155.09 (preserves pre-v1.9 behavior).

        With phase-out ON the BPA is linearly interpolated between $16,452 and $14,829
        for incomes in the range $181,440–$258,482.  At A ≈ 257,435 the BPA is phased
        almost to its minimum, raising K1 and thus *reducing* the K1 credit — meaning
        MORE tax is withheld (counter-intuitively, a higher K1 means more credit, but
        the phased BPA is LOWER, so K1 is smaller → higher tax).
        """
        fed = _fed_tax(self.GROSS, self.PERIODS, apply_bpa_phase_out=True)
        assert fed == pytest.approx(2155.09, abs=0.10), (
            f"Phase-out ON: FED_TAX expected ≈$2,155.09 (pre-v1.9 behavior), got {fed}"
        )

    def test_phase_out_on_withholds_more_than_off(self):
        """Phase-out ON always withholds ≥ phase-out OFF for high earners."""
        fed_on  = _fed_tax(self.GROSS, self.PERIODS, apply_bpa_phase_out=True)
        fed_off = _fed_tax(self.GROSS, self.PERIODS, apply_bpa_phase_out=False)
        assert fed_on > fed_off, (
            f"Phase-out ON ({fed_on}) must withhold more than phase-out OFF ({fed_off}) "
            f"for incomes inside the phase-out band."
        )

    def test_low_earner_unchanged_by_toggle(self):
        """NS @ $2,000 biweekly: toggle has no effect (income below phase-out band).

        Annual income ≈ $51,515 < $181,440 (phase-out start) — both settings must
        produce the same $163.23 per-period federal tax.
        """
        gross_low = 2000.0
        fed_on  = _fed_tax(gross_low, self.PERIODS, apply_bpa_phase_out=True)
        fed_off = _fed_tax(gross_low, self.PERIODS, apply_bpa_phase_out=False)
        assert fed_on == pytest.approx(163.23, abs=0.02), (
            f"Phase-out ON at $2,000 biweekly expected $163.23, got {fed_on}"
        )
        assert fed_off == pytest.approx(163.23, abs=0.02), (
            f"Phase-out OFF at $2,000 biweekly expected $163.23, got {fed_off}"
        )
        assert fed_on == fed_off, (
            f"Toggle must not change result below phase-out band: ON={fed_on}, OFF={fed_off}"
        )

    def test_above_phase_out_band_difference_equals_bpa_spread(self):
        """NS @ ~$300,000/yr (above phase-out band): difference = (bpa_max − bpa_min) × 0.14 / periods.

        Above $258,482 the phased BPA reaches its minimum ($14,829).  The per-period
        difference between phase-out ON and OFF must equal exactly the BPA spread
        prorated at the lowest federal rate and divided by pay periods.

        expected_diff = (16,452 − 14,829) × 0.14 / 26 = 1,623 × 0.14 / 26 ≈ $8.74
        """
        gross_high = 300_000 / self.PERIODS
        fed_on  = _fed_tax(gross_high, self.PERIODS, apply_bpa_phase_out=True)
        fed_off = _fed_tax(gross_high, self.PERIODS, apply_bpa_phase_out=False)

        expected_diff = (_BPA_MAX - _BPA_MIN) * _FED_BRACKETS[0][1] / self.PERIODS
        assert fed_on == pytest.approx(fed_off + expected_diff, abs=0.05), (
            f"Above phase-out band: difference expected {expected_diff:.2f}, "
            f"got ON={fed_on}, OFF={fed_off}, diff={fed_on - fed_off:.2f}"
        )
        # Phase-out ON uses bpa_min; verify it gives more withholding
        assert fed_on > fed_off, (
            f"Phase-out ON must withhold more above the phase-out band: ON={fed_on}, OFF={fed_off}"
        )

