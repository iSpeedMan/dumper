"""
app/templating.py — Shared Jinja2Templates instance for all routes.

Import `templates` from here instead of creating a new Jinja2Templates()
in each route file.  This ensures that global functions (e.g. csrf_token)
are available in every template without per-route injection.
"""

from datetime import datetime

from fastapi.templating import Jinja2Templates

from app.security import csrf_token

# Single shared instance — all routes render templates through this object
templates = Jinja2Templates(directory="templates")

# Register security helpers as Jinja2 globals so any template can call them
# without the route handler explicitly passing them in the context dict.
templates.env.globals["csrf_token"] = csrf_token


# ---------------------------------------------------------------------------
# Custom Jinja2 filters
# ---------------------------------------------------------------------------

def _fmt_dt(value, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Format a datetime (or ISO string) to the application standard.

    Usage in templates:
        {{ some_dt | fmt_dt }}              → "19.07.2026 03:00"
        {{ some_dt | fmt_dt('%H:%M:%S') }}  → "03:00:00"
        {{ None    | fmt_dt }}              → "—"
    """
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return value  # Return raw string if unparseable
    if hasattr(value, "strftime"):
        return value.strftime(fmt)
    return str(value)


templates.env.filters["fmt_dt"] = _fmt_dt
