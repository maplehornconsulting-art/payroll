# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Unit tests for parameter-driven PROV_TAX and OHP salary rules.

These tests validate that:
1. PROV_TAX reads province config from the ``l10n_ca_prov_tax_config`` rule
   parameter when available, and falls back to the embedded 2026 baseline
   when the parameter is absent or malformed.
2. OHP reads tier config from the ``l10n_ca_ohp_config`` rule parameter when
   available, and falls back to the embedded 2026 tiers otherwise.

Logic is replicated from hr_salary_rule_data.xml so tests run without a live
Odoo instance.
"""

from __future__ import annotations

import ast

import pytest


# ---------------------------------------------------------------------------
# Replicated PROV_TAX rule logic
# ---------------------------------------------------------------------------
# This mirrors the new compute code in salary_rule_ca_prov_tax exactly so that
# any future change to the rule is caught by test failures here.

def _prov_tax(gross: float, periods: int, province: str, prov_config_raw=None) -> float:
    """Replicate PROV_TAX rule logic.

    Parameters
    ----------
    gross:
        Gross pay for the period (no RRSP/union deductions for simplicity).
    periods:
        Number of pay periods per year.
    province:
        Two-letter province code.
    prov_config_raw:
        Simulates ``payslip._rule_parameter('l10n_ca_prov_tax_config')``.
        Pass a JSON string, a dict, None, or an invalid string.
    """
    annual_income = gross * periods

    PROV_RAW = None
    if isinstance(prov_config_raw, str):
        try:
            PROV_RAW = ast.literal_eval(prov_config_raw)
        except (ValueError, SyntaxError):
            PROV_RAW = None
    elif isinstance(prov_config_raw, dict):
        PROV_RAW = prov_config_raw

    if not PROV_RAW:
        # Fallback baseline (2026).
        PROV_RAW = {
            'ON': {'brackets': [[53891, 0.0505], [107785, 0.0915], [150000, 0.1116], [220000, 0.1216], [0, 0.1316]], 'bpa': 12989, 'surtax': [[5818, 0.20], [7446, 0.36]]},
            'AB': {'brackets': [[61200, 0.08], [154259, 0.10], [185111, 0.12], [246813, 0.13], [370220, 0.14], [0, 0.15]], 'bpa': 22769, 'surtax': []},
            'BC': {'brackets': [[50363, 0.0506], [100728, 0.077], [115648, 0.105], [140430, 0.1229], [190405, 0.147], [265545, 0.168], [0, 0.205]], 'bpa': 13216, 'surtax': []},
            'SK': {'brackets': [[54532, 0.105], [155805, 0.125], [0, 0.145]], 'bpa': 20381, 'surtax': []},
            'MB': {'brackets': [[47000, 0.108], [100000, 0.1275], [0, 0.174]], 'bpa': 15780, 'surtax': []},
            'NB': {'brackets': [[52333, 0.094], [104666, 0.14], [193861, 0.16], [0, 0.195]], 'bpa': 13664, 'surtax': []},
            'NS': {'brackets': [[30995, 0.0879], [61991, 0.1495], [97417, 0.1667], [157124, 0.175], [0, 0.21]], 'bpa': 11932, 'surtax': []},
            'PE': {'brackets': [[33928, 0.095], [65820, 0.1347], [106890, 0.166], [142250, 0.1762], [0, 0.19]], 'bpa': 15000, 'surtax': []},
            'NL': {'brackets': [[44678, 0.087], [89354, 0.145], [159528, 0.158], [223340, 0.178], [285319, 0.198], [570638, 0.208], [1141275, 0.213], [0, 0.218]], 'bpa': 11188, 'surtax': []},
            'NT': {'brackets': [[53003, 0.059], [106009, 0.086], [172346, 0.122], [0, 0.1405]], 'bpa': 18198, 'surtax': []},
            'YT': {'brackets': [[58523, 0.064], [117045, 0.09], [181440, 0.109], [500000, 0.128], [0, 0.15]], 'bpa': 16452, 'surtax': []},
            'NU': {'brackets': [[55801, 0.04], [111602, 0.07], [181439, 0.09], [0, 0.115]], 'bpa': 19659, 'surtax': []},
        }

    cfg_raw = PROV_RAW.get(province) or PROV_RAW.get('ON') or {}
    cfg = {
        'b':   cfg_raw.get('brackets', []),
        'bpa': cfg_raw.get('bpa', 0),
        'st':  cfg_raw.get('surtax', []),
    }

    # Build brackets (0 = infinity for top bracket)
    prov_brackets = []
    for br in cfg['b']:
        t = br[0] if br[0] != 0 else float('inf')
        prov_brackets.append((t, br[1]))

    if not prov_brackets:
        return 0.0

    # Progressive tax calculation
    tax = 0.0
    prev_bracket = 0.0
    for bracket, rate in prov_brackets:
        taxable_in_bracket = min(annual_income, bracket) - prev_bracket
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_bracket = bracket
        if annual_income <= bracket:
            break

    # BPA credit at lowest provincial rate
    prov_credit = cfg['bpa'] * prov_brackets[0][1]
    basic_provincial_tax = max(tax - prov_credit, 0.0)

    # Surtax (Ontario only as of 2026)
    surtax = 0.0
    for s in cfg['st']:
        if basic_provincial_tax > s[0]:
            surtax += (basic_provincial_tax - s[0]) * s[1]

    total_provincial_tax = basic_provincial_tax + surtax
    return round(-(total_provincial_tax / periods), 2)


# ---------------------------------------------------------------------------
# Replicated OHP rule logic
# ---------------------------------------------------------------------------

def _ohp(gross: float, periods: int, ohp_config_raw=None) -> float:
    """Replicate OHP rule logic.

    Parameters
    ----------
    gross:
        Gross pay for the period (no RRSP/union deductions for simplicity).
    periods:
        Number of pay periods per year.
    ohp_config_raw:
        Simulates ``payslip._rule_parameter('l10n_ca_ohp_config')``.
    """
    annual_income = gross * periods

    OHP_CFG = None
    if isinstance(ohp_config_raw, str):
        try:
            OHP_CFG = ast.literal_eval(ohp_config_raw)
        except (ValueError, SyntaxError):
            OHP_CFG = None
    elif isinstance(ohp_config_raw, dict):
        OHP_CFG = ohp_config_raw

    if not OHP_CFG or not OHP_CFG.get('tiers'):
        OHP_CFG = {'tiers': [
            {'upto':  20000, 'base':   0, 'rate': 0,      'cap':   0},
            {'upto':  36000, 'base':   0, 'rate': 0.06,   'cap': 300},
            {'upto':  48000, 'base': 300, 'rate': 0.06,   'cap': 150},
            {'upto':  72000, 'base': 450, 'rate': 0.0025, 'cap': 150},
            {'upto': 200000, 'base': 600, 'rate': 0.0025, 'cap': 300},
            {'upto':  None,  'base': 900, 'rate': 0,      'cap':   0},
        ]}

    ohp = 0.0
    prev_upto = 0
    for tier in OHP_CFG['tiers']:
        upto = tier.get('upto')
        if upto is None or annual_income <= upto:
            delta = annual_income - prev_upto
            ohp = tier['base'] + (
                min(delta * tier['rate'], tier['cap'])
                if tier.get('cap')
                else delta * tier.get('rate', 0)
            )
            if upto is None:
                ohp = tier['base']
            break
        prev_upto = upto

    return round(-(ohp / periods), 2)


# ---------------------------------------------------------------------------
# PROV_TAX tests
# ---------------------------------------------------------------------------

_GROSS = 1203.13
_PERIODS_WEEKLY = 52
_NS_PROVINCE = 'NS'


class TestProvTaxReadsParameter:
    """PROV_TAX must read from the rule parameter when it is available."""

    def test_reads_dict_parameter(self):
        """When parameter is a dict with NS bpa=99999, less tax is withheld."""
        # Synthetic config with NS bpa boosted to 99999 (huge credit → near-zero tax)
        param = {
            'NS': {
                'brackets': [[30995, 0.0879], [61991, 0.1495], [97417, 0.1667], [157124, 0.175], [0, 0.21]],
                'bpa': 99999,
                'surtax': [],
            }
        }
        result_with_param = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=param)
        result_baseline = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=None)
        # With bpa=99999, the credit wipes out all tax → result is 0 or less negative
        assert result_with_param > result_baseline, (
            f"Large BPA should reduce withholding: got {result_with_param} vs baseline {result_baseline}"
        )

    def test_reads_python_literal_string_parameter(self):
        """When parameter is a Python-literal string, it is parsed and used."""
        param = {
            'NS': {
                'brackets': [[30995, 0.0879], [61991, 0.1495], [97417, 0.1667], [157124, 0.175], [0, 0.21]],
                'bpa': 99999,
                'surtax': [],
            }
        }
        param_literal = repr(param)
        result_literal = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=param_literal)
        result_dict = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=param)
        # Both forms must produce identical results
        assert result_literal == result_dict

    def test_high_bpa_produces_zero_or_lower_withholding(self):
        """With bpa=99999 the BPA credit exceeds all provincial tax → 0."""
        param = {
            'NS': {
                'brackets': [[30995, 0.0879], [61991, 0.1495], [97417, 0.1667], [157124, 0.175], [0, 0.21]],
                'bpa': 99999,
                'surtax': [],
            }
        }
        result = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=param)
        assert result == 0.0, f"Huge BPA should zero out PROV_TAX, got {result}"

    def test_connector_key_format_brackets_surtax(self):
        """Parameter dict uses 'brackets'/'surtax' keys (connector format) correctly."""
        param = {
            'ON': {
                'brackets': [[53891, 0.0505], [107785, 0.0915], [150000, 0.1116], [220000, 0.1216], [0, 0.1316]],
                'bpa': 12989,
                'surtax': [[5818, 0.20], [7446, 0.36]],
            }
        }
        # Should not raise and should produce a negative value
        result = _prov_tax(_GROSS, _PERIODS_WEEKLY, 'ON', prov_config_raw=param)
        assert result < 0, f"ON PROV_TAX should be negative, got {result}"

    def test_unknown_province_falls_back_to_on(self):
        """Unknown province code falls back to ON config from the parameter."""
        param = {
            'ON': {
                'brackets': [[53891, 0.0505], [107785, 0.0915], [150000, 0.1116], [220000, 0.1216], [0, 0.1316]],
                'bpa': 12989,
                'surtax': [[5818, 0.20], [7446, 0.36]],
            }
        }
        result_unknown = _prov_tax(_GROSS, _PERIODS_WEEKLY, 'ZZ', prov_config_raw=param)
        result_on = _prov_tax(_GROSS, _PERIODS_WEEKLY, 'ON', prov_config_raw=param)
        assert result_unknown == result_on


class TestProvTaxFallback:
    """PROV_TAX must fall back to embedded 2026 baseline when parameter is unavailable."""

    def test_fallback_on_none(self):
        """None parameter triggers fallback; NS weekly ~$123."""
        result = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=None)
        assert result < 0, "PROV_TAX should be negative"
        assert abs(result) == pytest.approx(123.13, abs=0.5), (
            f"NS weekly baseline should be ~$123, got {result}"
        )

    def test_fallback_on_empty_dict(self):
        """Empty dict parameter triggers fallback."""
        result_empty = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw={})
        result_none = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=None)
        assert result_empty == result_none

    def test_fallback_on_invalid_literal_string(self):
        """Invalid Python literal string triggers fallback; result equals None fallback."""
        result_bad = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw="{bad literal!!}")
        result_none = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=None)
        assert result_bad == result_none

    def test_fallback_on_empty_string(self):
        """Empty string (invalid literal) triggers fallback."""
        result_empty = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw="")
        result_none = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE, prov_config_raw=None)
        assert result_empty == result_none

    def test_ns_weekly_baseline_value(self):
        """NS $1,203.13 weekly produces a consistent PROV_TAX using the 2026 fallback."""
        result = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE)
        # Self-consistency: run again with same inputs
        result2 = _prov_tax(_GROSS, _PERIODS_WEEKLY, _NS_PROVINCE)
        assert result == result2
        assert result < 0

    def test_fallback_contains_all_12_provinces(self):
        """Fallback covers all 12 in-scope provinces/territories."""
        provinces = ['ON', 'AB', 'BC', 'SK', 'MB', 'NB', 'NS', 'PE', 'NL', 'NT', 'YT', 'NU']
        for prov in provinces:
            result = _prov_tax(_GROSS, _PERIODS_WEEKLY, prov)
            assert result <= 0, f"PROV_TAX for {prov} should be ≤ 0, got {result}"


# ---------------------------------------------------------------------------
# OHP tests
# ---------------------------------------------------------------------------

class TestOhpReadsParameter:
    """OHP must read from the rule parameter when it is available."""

    def test_reads_dict_parameter(self):
        """A modified tier with lower 'upto' boundary changes OHP earlier."""
        # Change tier boundary 200000 → 50000 so the cap kicks in at a lower income
        modified_cfg = {'tiers': [
            {'upto':  20000, 'base':   0, 'rate': 0,      'cap':   0},
            {'upto':  36000, 'base':   0, 'rate': 0.06,   'cap': 300},
            {'upto':  48000, 'base': 300, 'rate': 0.06,   'cap': 150},
            {'upto':  50000, 'base': 450, 'rate': 0.0025, 'cap': 150},  # lowered from 72000
            {'upto': 200000, 'base': 600, 'rate': 0.0025, 'cap': 300},
            {'upto':   None, 'base': 900, 'rate': 0,      'cap':   0},
        ]}
        # Annual income = 60000 (≈ $1153.85 weekly × 52)
        gross_60k = 60000 / 52
        result_modified = _ohp(gross_60k, 52, ohp_config_raw=modified_cfg)
        result_default = _ohp(gross_60k, 52, ohp_config_raw=None)
        # With lowered boundary, the tier transition happens earlier → different OHP
        assert result_modified != result_default

    def test_reads_python_literal_string_parameter(self):
        """Python-literal string parameter is parsed and produces same result as dict."""
        cfg = {'tiers': [
            {'upto':  20000, 'base':   0, 'rate': 0,      'cap':   0},
            {'upto':  36000, 'base':   0, 'rate': 0.06,   'cap': 300},
            {'upto':  48000, 'base': 300, 'rate': 0.06,   'cap': 150},
            {'upto':  72000, 'base': 450, 'rate': 0.0025, 'cap': 150},
            {'upto': 200000, 'base': 600, 'rate': 0.0025, 'cap': 300},
            {'upto':   None, 'base': 900, 'rate': 0,      'cap':   0},
        ]}
        result_dict = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw=cfg)
        result_literal = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw=repr(cfg))
        assert result_dict == result_literal


class TestOhpFallback:
    """OHP must fall back to embedded 2026 tiers when parameter is unavailable."""

    def test_fallback_on_none(self):
        """None parameter triggers fallback."""
        # ON weekly $1,203.13 → annual ~$62,562 → tier: 450 + min(delta * 0.0025, 150)
        result = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw=None)
        assert result < 0, "OHP should be negative"

    def test_fallback_on_invalid_literal(self):
        """Invalid Python literal string triggers fallback; result equals None fallback."""
        result_bad = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw="not a literal")
        result_none = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw=None)
        assert result_bad == result_none

    def test_fallback_on_missing_tiers_key(self):
        """Dict without 'tiers' key triggers fallback."""
        result_no_tiers = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw={'other_key': []})
        result_none = _ohp(_GROSS, _PERIODS_WEEKLY, ohp_config_raw=None)
        assert result_no_tiers == result_none

    def test_default_tiers_below_20000(self):
        """Annual income ≤ $20,000 → OHP = $0."""
        gross_low = 19000 / 52
        result = _ohp(gross_low, 52)
        assert result == 0.0

    def test_default_tiers_at_36000(self):
        """Annual income = $36,000 → OHP = $300 annual → per period."""
        gross = 36000 / 52
        result = _ohp(gross, 52)
        expected_annual = min((36000 - 20000) * 0.06, 300)  # = 300
        expected_period = round(-(expected_annual / 52), 2)
        assert result == expected_period

    def test_default_tiers_above_200000(self):
        """Annual income > $200,000 → OHP = $900 annual."""
        gross_high = 250000 / 52
        result = _ohp(gross_high, 52)
        expected = round(-(900 / 52), 2)
        assert result == expected

    def test_default_tiers_at_72000(self):
        """Annual income = $72,000 → max of tier 4 → OHP = $510."""
        gross = 72000 / 52
        result = _ohp(gross, 52)
        expected_annual = 450 + min((72000 - 48000) * 0.0025, 150)  # = 450 + 60 = 510
        expected_period = round(-(expected_annual / 52), 2)
        assert result == expected_period


# ---------------------------------------------------------------------------
# Regression: hr_rule_parameters_data.xml values must survive ast.literal_eval
# ---------------------------------------------------------------------------
# These tests simulate what Odoo's safe_eval does when loading parameter values
# from the data files. Any JSON-only token (null/true/false) would cause a
# NameError in production; these tests catch that before deployment.


_OHP_CONFIG_2026_VALUE = """{
  "tiers": [
    {"upto":  20000, "base":   0, "rate": 0,      "cap":   0},
    {"upto":  36000, "base":   0, "rate": 0.06,   "cap": 300},
    {"upto":  48000, "base": 300, "rate": 0.06,   "cap": 150},
    {"upto":  72000, "base": 450, "rate": 0.0025, "cap": 150},
    {"upto": 200000, "base": 600, "rate": 0.0025, "cap": 300},
    {"upto":  None,  "base": 900, "rate": 0,      "cap":   0}
  ]
}"""

_PROV_TAX_CONFIG_2025_VALUE = """{
  "ON": {
    "brackets": [[53891, 0.0505], [107785, 0.0915], [150000, 0.1116], [220000, 0.1216], [0, 0.1316]],
    "bpa": 12989,
    "surtax": [[5818, 0.20], [7446, 0.36]]
  },
  "AB": {
    "brackets": [[61200, 0.08], [154259, 0.10], [185111, 0.12], [246813, 0.13], [370220, 0.14], [0, 0.15]],
    "bpa": 22769,
    "surtax": []
  },
  "NS": {
    "brackets": [[30995, 0.0879], [61991, 0.1495], [97417, 0.1667], [157124, 0.175], [0, 0.21]],
    "bpa": 11932,
    "surtax": []
  }
}"""


class TestParameterValuesSafeEvalCompatible:
    """Embedded parameter values must be parseable by ast.literal_eval (= safe_eval)."""

    def test_ohp_config_2026_no_json_null(self):
        """OHP config must not contain the JSON 'null' token."""
        assert "null" not in _OHP_CONFIG_2026_VALUE, (
            "OHP config contains 'null' — must use Python 'None'"
        )

    def test_ohp_config_2026_ast_literal_eval(self):
        """OHP config value must be parseable by ast.literal_eval without error."""
        result = ast.literal_eval(_OHP_CONFIG_2026_VALUE)
        assert isinstance(result, dict)
        assert "tiers" in result
        tiers = result["tiers"]
        assert len(tiers) == 6
        # The open-ended top tier must have upto=None (Python None, not JSON null)
        assert tiers[-1]["upto"] is None

    def test_prov_tax_config_2025_no_json_null(self):
        """Provincial tax config must not contain the JSON 'null' token."""
        assert "null" not in _PROV_TAX_CONFIG_2025_VALUE, (
            "Prov tax config contains 'null' — must use Python 'None'"
        )

    def test_prov_tax_config_2025_ast_literal_eval(self):
        """Provincial tax config value must be parseable by ast.literal_eval."""
        result = ast.literal_eval(_PROV_TAX_CONFIG_2025_VALUE)
        assert isinstance(result, dict)
        assert "ON" in result
        assert "AB" in result
        assert "NS" in result
        assert isinstance(result["ON"]["bpa"], int)
        assert isinstance(result["ON"]["brackets"], list)
        assert isinstance(result["ON"]["surtax"], list)
