---
name: Shared Jinja2 templates instance
description: All routes use a single Jinja2Templates instance from app/templating.py to share globals like csrf_token.
---

# Shared Jinja2 Templates

## Rule
All route files import `templates` from `app/templating.py` — never create a new `Jinja2Templates(directory="templates")` inline.

## Why
Each `Jinja2Templates()` creates its own Jinja2 Environment. Globals (e.g. `csrf_token`) registered on one instance are not visible in another. The shared instance in `app/templating.py` registers all globals once.

## How to apply
When adding a new route file, replace:
```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")
```
with:
```python
from app.templating import templates
```

To add a new Jinja2 global (e.g. a helper function), add it in `app/templating.py`:
```python
templates.env.globals["my_helper"] = my_helper
```
