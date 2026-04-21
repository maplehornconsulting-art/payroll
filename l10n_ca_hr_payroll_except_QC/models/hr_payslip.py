# Part of MHC. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from odoo import api, models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _l10n_ca_ytd_amount(self, code):
        """Return the year-to-date total (as a positive float) for a salary rule
        code on prior confirmed payslips in the same calendar year.

        CRA mandates an *annual* (not per-period) contribution maximum for CPP,
        CPP2, and EI.  Each payslip must cap its contribution at the annual max
        *minus* what has already been deducted on earlier payslips in the same
        calendar year.  This method returns the accumulated positive amount so
        the calling rule can compute the remaining headroom:

            remaining = max(annual_max - ytd, 0)
            deduction = min(period_contribution, remaining)

        Search criteria:
          - Same employee as ``self``.
          - Same calendar year as ``self.date_from``.
          - Payslip state in ``('done', 'paid')`` — draft/cancelled slips are
            excluded so only locked, remitted payslips count.
          - ``slip_id.date_to < self.date_from`` — only payslips that ended
            *before* the current payslip's start date.
          - ``salary_rule_id.code == code``.
          - Excludes the current payslip itself (relevant when the payslip is
            being re-computed after confirmation).

        Args:
            code (str): Salary rule code, e.g. ``'CPP_EE'``, ``'EI_EE'``.

        Returns:
            float: Sum of ``abs(line.total)`` for all matching lines, 0.0 if none.
        """
        self.ensure_one()
        year = self.date_from.year
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('slip_id.state', 'in', ('done', 'paid')),
            ('slip_id.date_to', '<', self.date_from),
            ('slip_id.date_from', '>=', f'{year}-01-01'),
            ('salary_rule_id.code', '=', code),
        ]
        if self.id:
            domain.append(('slip_id.id', '!=', self.id))
        lines = self.env['hr.payslip.line'].search(domain)
        return sum(abs(line.total) for line in lines)

    def _l10n_ca_projected_annual_contribution(self, code, period_amount, annual_max):
        """Return the projected full-year contribution for a CPP/CPP2/EI rule.

        Used by FED_TAX (K2) and PROV_TAX (K2P) to compute the non-refundable
        credit on the employee's *true* annual contribution rather than naively
        annualizing only the current period.

        Computation::

            ytd        = _l10n_ca_ytd_amount(code)              # prior periods
            current    = abs(period_amount)                     # this period
            remaining  = max(periods - periods_elapsed - 1, 0)  # future periods
            projected  = ytd + current + remaining * current
            return min(projected, annual_max)

        Where ``periods_elapsed`` is the count of prior done/paid payslips for
        the same employee in the same calendar year.  The "remaining * current"
        extrapolation assumes the rest of the year continues at the current
        period's contribution rate, which matches CRA T4127's per-period
        formula assumption while still respecting the annual cap.

        Args:
            code (str): Rule code, one of ``'CPP_EE'``, ``'CPP2_EE'``,
                ``'EI_EE'``.
            period_amount (float): Current period's contribution (positive or
                negative; abs() is taken internally).
            annual_max (float): Annual statutory maximum for the contribution.

        Returns:
            float: Projected full-year contribution, never exceeding
                ``annual_max``.
        """
        self.ensure_one()
        ytd = self._l10n_ca_ytd_amount(code)
        current = abs(period_amount or 0.0)
        periods = self._l10n_ca_periods_per_year() or 1
        year = self.date_from.year
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('state', 'in', ('done', 'paid')),
            ('date_to', '<', self.date_from),
            ('date_from', '>=', f'{year}-01-01'),
        ]
        if self.id:
            domain.append(('id', '!=', self.id))
        periods_elapsed = self.env['hr.payslip'].search_count(domain)
        remaining = max(periods - periods_elapsed - 1, 0)
        projected = ytd + current + remaining * current
        return min(projected, annual_max)

    def _l10n_ca_periods_per_year(self):
        """Return the number of pay periods per year for this payslip's schedule.

        Reads the schedule from the Structure Type's ``default_schedule_pay``
        field, falling back to the contract's ``schedule_pay``, and finally to
        bi-weekly (26) if neither is set.
        """
        self.ensure_one()
        mapping = {
            'annually': 1,
            'semi-annually': 2,
            'quarterly': 4,
            'bi-monthly': 6,
            'monthly': 12,
            'semi-monthly': 24,
            'bi-weekly': 26,
            'weekly': 52,
            'daily': 260,
        }
        # Prefer the actual schedule on the employee's contract/version
        # (Odoo 19 renamed contract_id -> version_id). Only fall back to
        # the structure type's default if neither is set.
        sp = None
        if hasattr(self, 'version_id') and self.version_id:
            sp = self.version_id.schedule_pay
        elif hasattr(self, 'contract_id') and self.contract_id:
            sp = self.contract_id.schedule_pay
        if not sp and self.struct_id.type_id:
            sp = self.struct_id.type_id.default_schedule_pay
        if not sp:
            sp = 'bi-weekly'
        return mapping.get(sp, 26)

    def _get_paid_amount(self):
        self.ensure_one()
        if self.struct_id.country_id.code != 'CA':
            return super()._get_paid_amount()

        # Hourly path: sum worked-days lines (WORK100 + LEAVE90)
        total = sum(
            line.amount for line in self.worked_days_line_ids
            if line.code in ('WORK100', 'LEAVE90')
        )
        if total > 0:
            return total

        # Salaried / fallback path
        base = super()._get_paid_amount() or 0.0

        # Detect monthly wage_type and scale to the actual pay period so that
        # annualization in FED_TAX/PROV_TAX sees the correct per-period BASIC.
        wage_type = None
        if hasattr(self, 'version_id') and self.version_id and 'wage_type' in self.version_id._fields:
            wage_type = self.version_id.wage_type
        elif hasattr(self, 'contract_id') and self.contract_id and 'wage_type' in self.contract_id._fields:
            wage_type = self.contract_id.wage_type
        if not wage_type and self.struct_id.type_id and 'wage_type' in self.struct_id.type_id._fields:
            wage_type = self.struct_id.type_id.wage_type

        if wage_type == 'monthly':
            periods = self._l10n_ca_periods_per_year() or 12
            return round(base * 12.0 / periods, 2)

        return base

    def _l10n_ca_ytd_pensionable_earnings(self):
        """Return YTD CPP pensionable earnings from prior confirmed payslips.

        CPP2 triggers only when the employee's cumulative pensionable earnings
        exceed the annual YMPE (T4127 §4.4).  This helper sums the per-period
        pensionable amounts from prior done/paid payslips in the same calendar
        year:

            pensionable_per_slip = max(GROSS − period_exemption, 0)

        The result is used by the CPP2_EE rule to determine whether this period
        lands in the YMPE → CPP2-ceiling band.

        Returns:
            float: Year-to-date pensionable earnings (positive), 0.0 if none.
        """
        self.ensure_one()
        try:
            cpp_exemption = self._rule_parameter('l10n_ca_cpp_basic_exemption')
        except Exception:
            cpp_exemption = 3500.0
        periods = self._l10n_ca_periods_per_year() or 1
        period_exemption = cpp_exemption / periods

        year = self.date_from.year
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('state', 'in', ('done', 'paid')),
            ('date_to', '<', self.date_from),
            ('date_from', '>=', f'{year}-01-01'),
        ]
        if self.id:
            domain.append(('id', '!=', self.id))
        prior_slips = self.env['hr.payslip'].search(domain)

        ytd_pensionable = 0.0
        for slip in prior_slips:
            gross_lines = slip.line_ids.filtered(lambda l: l.code == 'GROSS')
            gross_val = sum(abs(line.total) for line in gross_lines)
            ytd_pensionable += max(gross_val - period_exemption, 0.0)
        return ytd_pensionable

    def _l10n_ca_get_payslip_line_values(self, code_list, employee_id=None, compute_sum=False):
        """Compute Canadian payroll line values using rule parameters."""
        if not employee_id:
            return defaultdict(lambda: defaultdict(float))
        payslip = self.filtered(lambda p: p.employee_id.id == employee_id)
        if not payslip:
            return defaultdict(lambda: defaultdict(float))
        payslip = payslip[0]

        result = defaultdict(lambda: defaultdict(float))
        date_from = payslip.date_from

        # Get rule parameters
        def get_param(code, fallback=0):
            try:
                return payslip._rule_parameter(code)
            except Exception:
                return fallback

        # CPP parameters
        cpp_rate = get_param('l10n_ca_cpp_employee_rate', 0.0595)
        cpp_ympe = get_param('l10n_ca_cpp_ympe', 74600)
        cpp_exemption = get_param('l10n_ca_cpp_basic_exemption', 3500)
        cpp_max = get_param('l10n_ca_cpp_max_contribution', 4230.45)

        # CPP2 parameters
        cpp2_rate = get_param('l10n_ca_cpp2_rate', 0.04)
        cpp2_ceiling = get_param('l10n_ca_cpp2_ceiling', 85000)
        cpp2_max = get_param('l10n_ca_cpp2_max_contribution', 416.00)

        # EI parameters
        ei_rate = get_param('l10n_ca_ei_employee_rate', 0.0163)
        ei_max_premium = get_param('l10n_ca_ei_max_premium', 1123.07)
        ei_employer_mult = get_param('l10n_ca_ei_employer_multiplier', 1.4)

        # Federal tax brackets (threshold, rate)
        fed_brackets = [
            (get_param('l10n_ca_fed_bracket_1', 58523), get_param('l10n_ca_fed_rate_1', 0.14)),
            (get_param('l10n_ca_fed_bracket_2', 117045), get_param('l10n_ca_fed_rate_2', 0.205)),
            (get_param('l10n_ca_fed_bracket_3', 181440), get_param('l10n_ca_fed_rate_3', 0.26)),
            (get_param('l10n_ca_fed_bracket_4', 258482), get_param('l10n_ca_fed_rate_4', 0.29)),
            (float('inf'), get_param('l10n_ca_fed_rate_5', 0.33)),
        ]
        fed_bpa = get_param('l10n_ca_fed_basic_personal_amount', 16452)

        # Ontario provincial tax brackets (default)
        prov_brackets = [
            (get_param('l10n_ca_on_bracket_1', 52886), get_param('l10n_ca_on_rate_1', 0.0505)),
            (get_param('l10n_ca_on_bracket_2', 105775), get_param('l10n_ca_on_rate_2', 0.0915)),
            (get_param('l10n_ca_on_bracket_3', 150000), get_param('l10n_ca_on_rate_3', 0.1116)),
            (get_param('l10n_ca_on_bracket_4', 220000), get_param('l10n_ca_on_rate_4', 0.1216)),
            (float('inf'), get_param('l10n_ca_on_rate_5', 0.1316)),
        ]

        gross = payslip._get_line_values(['GROSS'], compute_sum=True)
        gross_amount = gross.get('GROSS', {}).get(payslip.id, {}).get('total', 0)

        periods = payslip._l10n_ca_periods_per_year()

        # Pre-compute employee contributions needed for employer calculations
        employer_deps = {
            'CPP_ER': 'CPP_EE',
            'CPP2_ER': 'CPP2_EE',
            'EI_ER': 'EI_EE',
        }
        for code in code_list:
            dep = employer_deps.get(code)
            if dep and dep not in code_list and dep not in result:
                dep_result = self._l10n_ca_get_payslip_line_values([dep], employee_id=employee_id)
                result[dep][payslip.id] = dep_result[dep].get(payslip.id, {'total': 0})

        for code in code_list:
            if code == 'CPP_EE':
                if payslip.version_id.l10n_ca_cpp_exempt:
                    result[code][payslip.id] = {'total': 0}
                    continue
                period_exemption = cpp_exemption / periods
                pensionable = max(gross_amount - period_exemption, 0)
                period_contribution = pensionable * cpp_rate
                # CRA: annual cumulative cap, NOT per-period cap.
                ytd_cpp = payslip._l10n_ca_ytd_amount('CPP_EE')
                remaining_annual = max(cpp_max - ytd_cpp, 0)
                cpp_contribution = min(period_contribution, remaining_annual)
                result[code][payslip.id] = {'total': round(cpp_contribution, 2)}

            elif code == 'CPP2_EE':
                if payslip.version_id.l10n_ca_cpp_exempt:
                    result[code][payslip.id] = {'total': 0}
                    continue
                period_exemption = cpp_exemption / periods
                # CRA T4127 §4.4: CPP2 applies only once YTD pensionable
                # earnings exceed the annual YMPE.  Use cumulative approach.
                ytd_pensionable = payslip._l10n_ca_ytd_pensionable_earnings()
                period_pensionable = max(gross_amount - period_exemption, 0)
                new_ytd_pensionable = ytd_pensionable + period_pensionable
                if new_ytd_pensionable <= cpp_ympe:
                    cpp2_contribution = 0
                else:
                    band_low = max(ytd_pensionable, cpp_ympe)
                    band_high = min(new_ytd_pensionable, cpp2_ceiling)
                    cpp2_pensionable_period = max(band_high - band_low, 0)
                    period_contribution = cpp2_pensionable_period * cpp2_rate
                    # CRA: annual cumulative cap, NOT per-period cap.
                    ytd_cpp2 = payslip._l10n_ca_ytd_amount('CPP2_EE')
                    remaining_annual = max(cpp2_max - ytd_cpp2, 0)
                    cpp2_contribution = min(period_contribution, remaining_annual)
                result[code][payslip.id] = {'total': round(cpp2_contribution, 2)}

            elif code == 'EI_EE':
                if payslip.version_id.l10n_ca_ei_exempt:
                    result[code][payslip.id] = {'total': 0}
                    continue
                # CRA T4127 §4.1: EI premium = gross × rate.  The only cap
                # is the annual premium maximum; no per-period insurable cap.
                period_premium = gross_amount * ei_rate
                ytd_ei = payslip._l10n_ca_ytd_amount('EI_EE')
                remaining_annual = max(ei_max_premium - ytd_ei, 0)
                ei_premium = min(period_premium, remaining_annual)
                result[code][payslip.id] = {'total': round(ei_premium, 2)}

            elif code == 'FED_TAX':
                annual_income = gross_amount * periods
                tax = self._compute_progressive_tax(annual_income, fed_brackets)
                credit = fed_bpa * fed_brackets[0][1]  # BPA credit at lowest bracket rate
                annual_tax = max(tax - credit, 0)
                additional = payslip.version_id.l10n_ca_additional_tax or 0
                result[code][payslip.id] = {'total': round(annual_tax / periods + additional, 2)}

            elif code == 'PROV_TAX':
                annual_income = gross_amount * periods
                tax = self._compute_progressive_tax(annual_income, prov_brackets)
                result[code][payslip.id] = {'total': round(tax / periods, 2)}

            elif code == 'CPP_ER':
                cpp_ee = result.get('CPP_EE', {}).get(payslip.id, {}).get('total', 0)
                result[code][payslip.id] = {'total': round(cpp_ee, 2)}

            elif code == 'CPP2_ER':
                cpp2_ee = result.get('CPP2_EE', {}).get(payslip.id, {}).get('total', 0)
                result[code][payslip.id] = {'total': round(cpp2_ee, 2)}

            elif code == 'EI_ER':
                ei_ee = result.get('EI_EE', {}).get(payslip.id, {}).get('total', 0)
                result[code][payslip.id] = {'total': round(ei_ee * ei_employer_mult, 2)}

        return result

    @staticmethod
    def _compute_progressive_tax(income, brackets):
        """Compute progressive tax given income and list of (threshold, rate) tuples."""
        tax = 0
        prev_threshold = 0
        for threshold, rate in brackets:
            taxable = min(income, threshold) - prev_threshold
            if taxable <= 0:
                break
            tax += taxable * rate
            prev_threshold = threshold
        return tax

    # ------------------------------------------------------------------
    # Salary-rule compute helpers — one per CA rule code.
    # Both the Hourly and Salaried XML rule records call these helpers so
    # the actual computation lives in a single Python place and is never
    # duplicated between structures.
    # ------------------------------------------------------------------

    def _l10n_ca_compute_basic(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        return self._get_paid_amount()

    def _l10n_ca_compute_ot(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if inputs is None:
            inputs = {}
        ot_from_worked_days = sum(line.amount for line in self.worked_days_line_ids if line.code == 'OVERTIME')
        ot_from_input = inputs['OT'].amount if inputs.get('OT') and inputs['OT'].amount > 0 else 0
        return ot_from_worked_days + ot_from_input

    def _l10n_ca_compute_sto(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        return worked_days.get('LEAVE110').amount if worked_days and worked_days.get('LEAVE110') else 0

    def _l10n_ca_compute_pto(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        return worked_days.get('LEAVE120').amount if worked_days and worked_days.get('LEAVE120') else 0

    def _l10n_ca_compute_cto(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        return worked_days.get('LEAVE105').amount if worked_days and worked_days.get('LEAVE105') else 0

    def _l10n_ca_compute_vac_pay(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        if inputs is None:
            inputs = {}
        vac_pay_rate = float(self._rule_parameter('l10n_ca_vacation_pay_rate') or 0.04)
        basic = float(result_rules.get('BASIC', {}).get('total', 0))
        ot = float(result_rules.get('OT', {}).get('total', 0))
        bonus = float(inputs['BONUS'].amount) if inputs.get('BONUS') else 0.0
        commission = float(inputs['COMMISSION'].amount) if inputs.get('COMMISSION') else 0.0
        vacationable_earnings = basic + ot + bonus + commission
        if inputs.get('VAC_PAY') and inputs['VAC_PAY'].amount > 0:
            return round(float(inputs['VAC_PAY'].amount), 2)
        return round(vacationable_earnings * vac_pay_rate, 2)

    def _l10n_ca_compute_gross(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        if inputs is None:
            inputs = {}
        return (
            result_rules.get('BASIC', {}).get('total', 0)
            + result_rules.get('VAC_PAY', {}).get('total', 0)
            + result_rules.get('OT', {}).get('total', 0)
            + result_rules.get('STO', {}).get('total', 0)
            + result_rules.get('PTO', {}).get('total', 0)
            + result_rules.get('CTO', {}).get('total', 0)
            + (inputs['BONUS'].amount if inputs.get('BONUS') else 0)
            + (inputs['COMMISSION'].amount if inputs.get('COMMISSION') else 0)
        )

    def _l10n_ca_compute_rrsp(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if inputs is None:
            inputs = {}
        return -(inputs['RRSP'].amount if inputs.get('RRSP') else 0)

    def _l10n_ca_compute_union_dues(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if inputs is None:
            inputs = {}
        return -(inputs['UNION'].amount if inputs.get('UNION') else 0)

    def _l10n_ca_compute_cpp_ee(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        gross_amount = result_rules.get('GROSS', {}).get('total', 0)
        version = self.version_id
        if version and version.l10n_ca_cpp_exempt:
            return 0
        periods = self._l10n_ca_periods_per_year()
        cpp_rate = self._rule_parameter('l10n_ca_cpp_employee_rate')
        cpp_exemption = self._rule_parameter('l10n_ca_cpp_basic_exemption')
        cpp_max = self._rule_parameter('l10n_ca_cpp_max_contribution')
        period_exemption = cpp_exemption / periods
        pensionable = max(gross_amount - period_exemption, 0)
        period_contribution = pensionable * cpp_rate
        ytd_cpp = self._l10n_ca_ytd_amount('CPP_EE')
        remaining_annual = max(cpp_max - ytd_cpp, 0)
        return -min(period_contribution, remaining_annual)

    def _l10n_ca_compute_cpp2_ee(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        gross_amount = result_rules.get('GROSS', {}).get('total', 0)
        version = self.version_id
        if version and version.l10n_ca_cpp_exempt:
            return 0
        periods = self._l10n_ca_periods_per_year()
        cpp_exemption = self._rule_parameter('l10n_ca_cpp_basic_exemption')
        cpp_ympe = self._rule_parameter('l10n_ca_cpp_ympe')
        cpp2_rate = self._rule_parameter('l10n_ca_cpp2_rate')
        cpp2_ceiling = self._rule_parameter('l10n_ca_cpp2_ceiling')
        cpp2_max = self._rule_parameter('l10n_ca_cpp2_max_contribution')
        period_exemption = cpp_exemption / periods
        ytd_pensionable = self._l10n_ca_ytd_pensionable_earnings()
        period_pensionable = max(gross_amount - period_exemption, 0)
        new_ytd_pensionable = ytd_pensionable + period_pensionable
        if new_ytd_pensionable <= cpp_ympe:
            return 0
        band_low = max(ytd_pensionable, cpp_ympe)
        band_high = min(new_ytd_pensionable, cpp2_ceiling)
        cpp2_pensionable = max(band_high - band_low, 0)
        period_contribution = cpp2_pensionable * cpp2_rate
        ytd_cpp2 = self._l10n_ca_ytd_amount('CPP2_EE')
        remaining_annual = max(cpp2_max - ytd_cpp2, 0)
        return -min(period_contribution, remaining_annual)

    def _l10n_ca_compute_ei_ee(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        gross_amount = result_rules.get('GROSS', {}).get('total', 0)
        version = self.version_id
        if version and version.l10n_ca_ei_exempt:
            return 0
        ei_rate = self._rule_parameter('l10n_ca_ei_employee_rate')
        ei_max_premium = self._rule_parameter('l10n_ca_ei_max_premium')
        period_premium = gross_amount * ei_rate
        ytd_ei = self._l10n_ca_ytd_amount('EI_EE')
        remaining_annual = max(ei_max_premium - ytd_ei, 0)
        return -min(period_premium, remaining_annual)

    def _l10n_ca_compute_fed_tax(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        gross_amount = result_rules.get('GROSS', {}).get('total', 0)
        rrsp = abs(result_rules.get('RRSP', {}).get('total', 0))
        union = abs(result_rules.get('UNION_DUES', {}).get('total', 0))
        taxable_per_period = gross_amount - rrsp - union
        periods = self._l10n_ca_periods_per_year()

        cpp_total_rate = self._rule_parameter('l10n_ca_cpp_employee_rate')
        cpp_base_rate = self._rule_parameter('l10n_ca_cpp_base_rate')
        cea = self._rule_parameter('l10n_ca_fed_canada_employment_amount')
        cpp_max = self._rule_parameter('l10n_ca_cpp_max_contribution')
        ei_max = self._rule_parameter('l10n_ca_ei_max_premium')
        annual_cpp = self._l10n_ca_projected_annual_contribution(
            'CPP_EE', result_rules.get('CPP_EE', {}).get('total', 0), cpp_max)
        annual_ei = self._l10n_ca_projected_annual_contribution(
            'EI_EE', result_rules.get('EI_EE', {}).get('total', 0), ei_max)
        annual_cpp_base = annual_cpp * (cpp_base_rate / cpp_total_rate) if cpp_total_rate else 0.0

        period_cpp = abs(result_rules.get('CPP_EE', {}).get('total', 0))
        period_enhanced_cpp = period_cpp * ((cpp_total_rate - cpp_base_rate) / cpp_total_rate) if cpp_total_rate else 0.0
        annual_enhanced_cpp = period_enhanced_cpp * periods

        period_cpp2 = abs(result_rules.get('CPP2_EE', {}).get('total', 0))
        annual_cpp2_full = period_cpp2 * periods

        annual_income = taxable_per_period * periods - annual_enhanced_cpp - annual_cpp2_full

        fed_brackets = [
            (self._rule_parameter('l10n_ca_fed_bracket_1'), self._rule_parameter('l10n_ca_fed_rate_1')),
            (self._rule_parameter('l10n_ca_fed_bracket_2'), self._rule_parameter('l10n_ca_fed_rate_2')),
            (self._rule_parameter('l10n_ca_fed_bracket_3'), self._rule_parameter('l10n_ca_fed_rate_3')),
            (self._rule_parameter('l10n_ca_fed_bracket_4'), self._rule_parameter('l10n_ca_fed_rate_4')),
            (float('inf'), self._rule_parameter('l10n_ca_fed_rate_5')),
        ]

        bpa_max = self._rule_parameter('l10n_ca_fed_basic_personal_amount')
        bpa_min = self._rule_parameter('l10n_ca_fed_bpa_min')
        phase_out_start = self._rule_parameter('l10n_ca_fed_bracket_3')
        phase_out_end = self._rule_parameter('l10n_ca_fed_bracket_4')

        version = self.version_id
        if version and version.l10n_ca_apply_bpa_phase_out:
            if annual_income <= phase_out_start:
                fed_bpa = bpa_max
            elif annual_income >= phase_out_end:
                fed_bpa = bpa_min
            else:
                fed_bpa = bpa_max - (bpa_max - bpa_min) * (annual_income - phase_out_start) / (phase_out_end - phase_out_start)
        else:
            fed_bpa = bpa_max

        tax = 0
        prev_bracket = 0
        for bracket, rate in fed_brackets:
            taxable_in_bracket = min(annual_income, bracket) - prev_bracket
            if taxable_in_bracket > 0:
                tax += taxable_in_bracket * rate
            prev_bracket = bracket
            if annual_income <= bracket:
                break

        credit = (fed_bpa + cea) * fed_brackets[0][1]
        k2 = (annual_cpp_base + annual_ei) * fed_brackets[0][1]
        annual_tax = max(tax - credit - k2, 0)
        additional = (version.l10n_ca_additional_tax if version else 0) or 0
        return -(annual_tax / periods + additional)

    def _l10n_ca_compute_prov_tax(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        gross_amount = result_rules.get('GROSS', {}).get('total', 0)
        rrsp = abs(result_rules.get('RRSP', {}).get('total', 0))
        union = abs(result_rules.get('UNION_DUES', {}).get('total', 0))
        taxable_per_period = gross_amount - rrsp - union
        periods = self._l10n_ca_periods_per_year()

        province = self.employee_id.l10n_ca_province_id.code or 'ON'

        prov_config_raw = self._rule_parameter('l10n_ca_prov_tax_config')
        PROV_RAW = prov_config_raw if isinstance(prov_config_raw, dict) else None

        if not PROV_RAW:
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
            'b': cfg_raw.get('brackets', []),
            'bpa': cfg_raw.get('bpa', 0),
            'st': cfg_raw.get('surtax', []),
        }

        prov_brackets = []
        for br in cfg['b']:
            t = br[0] if br[0] != 0 else float('inf')
            prov_brackets.append((t, br[1]))

        cpp_total_rate_p = self._rule_parameter('l10n_ca_cpp_employee_rate')
        cpp_base_rate_p = self._rule_parameter('l10n_ca_cpp_base_rate')
        cpp_max_p = self._rule_parameter('l10n_ca_cpp_max_contribution')
        ei_max_p = self._rule_parameter('l10n_ca_ei_max_premium')
        annual_cpp_p = self._l10n_ca_projected_annual_contribution(
            'CPP_EE', result_rules.get('CPP_EE', {}).get('total', 0), cpp_max_p)
        annual_ei_p = self._l10n_ca_projected_annual_contribution(
            'EI_EE', result_rules.get('EI_EE', {}).get('total', 0), ei_max_p)
        annual_cpp_base_p = annual_cpp_p * (cpp_base_rate_p / cpp_total_rate_p) if cpp_total_rate_p else 0.0

        period_cpp_p = abs(result_rules.get('CPP_EE', {}).get('total', 0))
        period_enhanced_cpp_p = period_cpp_p * ((cpp_total_rate_p - cpp_base_rate_p) / cpp_total_rate_p) if cpp_total_rate_p else 0.0
        annual_enhanced_cpp_p = period_enhanced_cpp_p * periods

        period_cpp2_p = abs(result_rules.get('CPP2_EE', {}).get('total', 0))
        annual_cpp2_full_p = period_cpp2_p * periods

        annual_income = taxable_per_period * periods - annual_enhanced_cpp_p - annual_cpp2_full_p

        tax = 0
        prev_bracket = 0
        for bracket, rate in prov_brackets:
            taxable_in_bracket = min(annual_income, bracket) - prev_bracket
            if taxable_in_bracket > 0:
                tax += taxable_in_bracket * rate
            prev_bracket = bracket
            if annual_income <= bracket:
                break

        prov_credit = cfg['bpa'] * prov_brackets[0][1]
        k2p = (annual_cpp_base_p + annual_ei_p) * prov_brackets[0][1]
        basic_provincial_tax = max(tax - prov_credit - k2p, 0)

        surtax = 0
        for s in cfg['st']:
            if basic_provincial_tax > s[0]:
                surtax += (basic_provincial_tax - s[0]) * s[1]

        total_provincial_tax = basic_provincial_tax + surtax
        return -(total_provincial_tax / periods)

    def _l10n_ca_compute_ohp(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        gross_amount = result_rules.get('GROSS', {}).get('total', 0)
        rrsp = abs(result_rules.get('RRSP', {}).get('total', 0))
        union = abs(result_rules.get('UNION_DUES', {}).get('total', 0))
        taxable_per_period = gross_amount - rrsp - union
        periods = self._l10n_ca_periods_per_year()
        annual_income = taxable_per_period * periods

        ohp_config_raw = self._rule_parameter('l10n_ca_ohp_config')
        OHP_CFG = ohp_config_raw if isinstance(ohp_config_raw, dict) else None

        if not OHP_CFG or not OHP_CFG.get('tiers'):
            OHP_CFG = {'tiers': [
                {'upto': 20000, 'base': 0, 'rate': 0, 'cap': 0},
                {'upto': 36000, 'base': 0, 'rate': 0.06, 'cap': 300},
                {'upto': 48000, 'base': 300, 'rate': 0.06, 'cap': 150},
                {'upto': 72000, 'base': 450, 'rate': 0.25, 'cap': 150},
                {'upto': 200000, 'base': 600, 'rate': 0.25, 'cap': 300},
                {'upto': None, 'base': 900, 'rate': 0, 'cap': 0},
            ]}

        ohp = 0
        prev_upto = 0
        for tier in OHP_CFG['tiers']:
            upto = tier.get('upto')
            if upto is None or annual_income <= upto:
                delta = annual_income - prev_upto
                ohp = tier['base'] + (min(delta * tier['rate'], tier['cap']) if tier.get('cap') else delta * tier.get('rate', 0))
                if upto is None:
                    ohp = tier['base']
                break
            prev_upto = upto

        return -(ohp / periods)

    def _l10n_ca_compute_net(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        return (
            result_rules.get('GROSS', {}).get('total', 0)
            - abs(result_rules.get('RRSP', {}).get('total', 0))
            - abs(result_rules.get('UNION_DUES', {}).get('total', 0))
            - abs(result_rules.get('CPP_EE', {}).get('total', 0))
            - abs(result_rules.get('CPP2_EE', {}).get('total', 0))
            - abs(result_rules.get('EI_EE', {}).get('total', 0))
            - abs(result_rules.get('FED_TAX', {}).get('total', 0))
            - abs(result_rules.get('PROV_TAX', {}).get('total', 0))
            - abs(result_rules.get('OHP', {}).get('total', 0))
        )

    def _l10n_ca_compute_cpp_er(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        return -result_rules.get('CPP_EE', {}).get('total', 0)

    def _l10n_ca_compute_cpp2_er(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        return -result_rules.get('CPP2_EE', {}).get('total', 0)

    def _l10n_ca_compute_ei_er(self, result_rules=None, inputs=None, categories=None, worked_days=None):
        self.ensure_one()
        if result_rules is None:
            result_rules = {}
        ei_employer_mult = self._rule_parameter('l10n_ca_ei_employer_multiplier')
        return -result_rules.get('EI_EE', {}).get('total', 0) * ei_employer_mult
