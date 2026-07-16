---
name: Auth system
description: How authentication works in Dumper (session, local, LDAP, first-run).
---

## Design
- `starlette.middleware.sessions.SessionMiddleware` stores user_id + username in signed cookie (itsdangerous).
- `require_auth` dependency raises `_AuthRedirect` exception; registered exception handler returns 302 to /login.
- First run (0 users in DB): any route redirects to /setup. After admin created, /setup is locked.
- Local auth: bcrypt via `passlib[bcrypt]`. LDAP auth: `ldap3` (pure Python, no C extensions needed).
- LDAP settings stored in `app_settings` table (key/value). Toggled from /settings/ UI.

**Why ldap3 over python-ldap:** ldap3 is pure Python, no libldap2 system dep, works out of the box in Replit NixOS.

**How to apply:** All page routes use `user=Depends(require_auth)`. API routes that return JSON check Accept header and raise 401 instead of redirect.
