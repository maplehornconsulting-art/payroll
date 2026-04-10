# Part of MHC. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from odoo import api, models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_paid_amount(self):
        self.ensure_one()
        if self.struct_id.country_id.code == 'CA':
            return self._get_worked_days_line_amount('WORK100') + self._get_worked_days_line_amount('LEAVE90')
        return super()._get_paid_amount()

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
        ei_max_insurable = get_param('l10n_ca_ei_max_insurable', 68900)
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
                pensionable = min(gross_amount, cpp_ympe) - cpp_exemption
                if pensionable < 0:
                    pensionable = 0
                cpp_contribution = min(pensionable * cpp_rate, cpp_max)
                result[code][payslip.id] = {'total': round(cpp_contribution, 2)}

            elif code == 'CPP2_EE':
                if payslip.version_id.l10n_ca_cpp_exempt:
                    result[code][payslip.id] = {'total': 0}
                    continue
                if gross_amount > cpp_ympe:
                    cpp2_pensionable = min(gross_amount, cpp2_ceiling) - cpp_ympe
                    cpp2_contribution = min(cpp2_pensionable * cpp2_rate, cpp2_max)
                else:
                    cpp2_contribution = 0
                result[code][payslip.id] = {'total': round(cpp2_contribution, 2)}

            elif code == 'EI_EE':
                if payslip.version_id.l10n_ca_ei_exempt:
                    result[code][payslip.id] = {'total': 0}
                    continue
                insurable = min(gross_amount, ei_max_insurable)
                ei_premium = min(insurable * ei_rate, ei_max_premium)
                result[code][payslip.id] = {'total': round(ei_premium, 2)}

            elif code == 'FED_TAX':
                annual_income = gross_amount * 12  # Annualize monthly gross
                tax = self._compute_progressive_tax(annual_income, fed_brackets)
                credit = fed_bpa * fed_brackets[0][1]  # BPA credit at lowest bracket rate
                annual_tax = max(tax - credit, 0)
                additional = payslip.version_id.l10n_ca_additional_tax or 0
                result[code][payslip.id] = {'total': round(annual_tax / 12 + additional, 2)}

            elif code == 'PROV_TAX':
                annual_income = gross_amount * 12
                tax = self._compute_progressive_tax(annual_income, prov_brackets)
                result[code][payslip.id] = {'total': round(tax / 12, 2)}

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
