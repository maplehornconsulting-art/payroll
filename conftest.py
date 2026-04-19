# Part of MHC. See LICENSE file for full copyright and licensing details.
"""Root pytest configuration.

Installs lightweight Odoo stubs into ``sys.modules`` so that Odoo modules
(such as ``l10n_ca_hr_payroll_cra_connector``) can be imported in a plain
pytest / CI environment without a running Odoo server.

The stubs are only inserted when Odoo is not already present; a real Odoo
installation will take precedence.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock


def _install_odoo_stubs() -> None:
    if "odoo" in sys.modules:
        return  # Real Odoo or previous stub run — do nothing.

    # Root odoo package
    odoo = ModuleType("odoo")
    odoo._ = lambda s: s  # type: ignore[attr-defined]
    odoo.api = MagicMock(name="odoo.api")
    odoo.fields = MagicMock(name="odoo.fields")

    # odoo.models — provide a plain Model base class so the connector
    # classes can inherit from it without metaclass magic.
    models_mod = ModuleType("odoo.models")

    class Model:  # noqa: D101
        _name: str = ""
        _description: str = ""
        _inherit: list = []
        _order: str = ""

    class AbstractModel:  # noqa: D101
        _name: str = ""
        _description: str = ""

    class TransientModel:  # noqa: D101
        _name: str = ""
        _description: str = ""
        _inherit: list = []

    models_mod.Model = Model  # type: ignore[attr-defined]
    models_mod.AbstractModel = AbstractModel  # type: ignore[attr-defined]
    models_mod.TransientModel = TransientModel  # type: ignore[attr-defined]
    odoo.models = models_mod  # type: ignore[attr-defined]

    # odoo.exceptions
    exceptions_mod = ModuleType("odoo.exceptions")
    exceptions_mod.UserError = type("UserError", (Exception,), {})  # type: ignore[attr-defined]
    odoo.exceptions = exceptions_mod  # type: ignore[attr-defined]

    sys.modules["odoo"] = odoo
    sys.modules["odoo.models"] = models_mod
    sys.modules["odoo.fields"] = odoo.fields
    sys.modules["odoo.api"] = odoo.api
    sys.modules["odoo.exceptions"] = exceptions_mod


_install_odoo_stubs()
