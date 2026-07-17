---
name: Middleware ordering in main.py
description: Starlette reverses add_middleware order; the LAST call is outermost. SessionMiddleware must be outermost so session is loaded before CSRF runs.
---

# Middleware Ordering

## Rule
In `main.py`, add middleware in this order:
1. `app.add_middleware(CSRFMiddleware)` — first call → inner layer
2. `app.add_middleware(SessionMiddleware, ...)` — second call → outermost layer

## Why
Starlette's `add_middleware` prepends to the internal list. When building the stack it reverses the list, so the LAST `add_middleware` call becomes the OUTERMOST layer (processes requests first). SessionMiddleware must run first so it populates `request.session` before CSRFMiddleware tries to read the CSRF token from the session.

## How to apply
- Request flow: SessionMiddleware → CSRFMiddleware → route handler
- If adding more middleware that needs session access, add it AFTER SessionMiddleware in the file (it will be inner)
- If adding middleware that doesn't need session, it can go before or after
