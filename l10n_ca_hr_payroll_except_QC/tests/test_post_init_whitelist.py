# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Guard test: the _post_init_hook whitelist must include both hourly and
salaried xml IDs for BASIC, GROSS, NET. Missing the _salaried IDs caused
the v19.0.2.2 regression where the salaried structure shipped with only
16 rules instead of 19."""
import pathlib
import re


def test_post_init_whitelist_includes_all_six_xmlids():
    src = pathlib.Path(__file__).parent.parent.joinpath('__init__.py').read_text()
    required = [
        'salary_rule_ca_basic',
        'salary_rule_ca_basic_salaried',
        'salary_rule_ca_gross',
        'salary_rule_ca_gross_salaried',
        'salary_rule_ca_net',
        'salary_rule_ca_net_salaried',
    ]
    for xmlid in required:
        pattern = rf"'l10n_ca_hr_payroll_except_QC\.{xmlid}'"
        assert re.search(pattern, src), (
            f"_post_init_hook whitelist is missing '{xmlid}'. "
            f"Without it, the archive sweep will deactivate this rule on install."
        )
