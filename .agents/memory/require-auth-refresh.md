---
name: require_auth always refreshes from DB
description: require_auth re-fetches is_admin and is_active on every request; fixes setup-admin nav bug and prevents stale session privilege escalation.
---

# require_auth DB Refresh

## Rule
`app/auth.py::require_auth` always queries the DB for the current user's `is_admin` and `is_active` values on every authenticated request.

## Why
Two bugs this fixes:
1. The admin created via `/setup` wasn't reliably showing the Users nav button — the session value wasn't always set correctly at redirect time.
2. If an admin is demoted in the Users panel, their existing session would still have `is_admin=True` without this refresh.

## How to apply
After `get_session_user(request)` returns a user dict, the dependency does:
```python
db_user = db.get(User, user["id"])
if not db_user or not db_user.is_active:
    clear_session(request); raise _AuthRedirect("/login")
user["is_admin"] = bool(db_user.is_admin)
request.session["is_admin"] = bool(db_user.is_admin)
```
This means `require_auth` now requires the `db: Session = Depends(get_db)` parameter.
