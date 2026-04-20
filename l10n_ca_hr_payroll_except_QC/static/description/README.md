# static/description — Image Assets Required

Before submitting this module to the Odoo Apps Store, add the following image files to this directory:

| File | Size | Purpose |
|------|------|---------|
| `icon.png` | 128×128 px or 256×256 px | Module icon shown in the Odoo Apps menu and Apps Store |
| `banner.png` | 1024×500 px | Hero banner shown at the top of your Apps Store listing |
| `screenshot_01.png` | 1280×800 px (recommended) | Employee payslip with Canadian tax breakdown |
| `screenshot_02.png` | 1280×800 px (recommended) | Employee configuration (SIN, Province, TD1 Claim Codes) |
| `screenshot_03.png` | 1280×800 px (recommended) | Payroll structure / salary rules view |

These files are referenced in `index.html` and `__manifest__.py` but are not tracked in version control
(they should be added before packaging the module as a `.zip` for upload).
