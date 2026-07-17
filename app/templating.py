"""
app/templating.py — Shared Jinja2Templates instance for all routes.

Import `templates` from here instead of creating a new Jinja2Templates()
in each route file.  This ensures that global functions (e.g. csrf_token)
are available in every template without per-route injection.
"""

from fastapi.templating import Jinja2Templates

from app.security import csrf_token

# Single shared instance — all routes render templates through this object
templates = Jinja2Templates(directory="templates")

# Register security helpers as Jinja2 globals so any template can call them
# without the route handler explicitly passing them in the context dict.
templates.env.globals["csrf_token"] = csrf_token
