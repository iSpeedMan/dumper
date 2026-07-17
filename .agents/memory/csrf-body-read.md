---
name: CSRF middleware body reading in BaseHTTPMiddleware
description: Starlette 0.37 _CachedRequest.wrapped_receive replays self._body; safe to call request.form() in BaseHTTPMiddleware before call_next.
---

# CSRF Middleware Body Reading

## Rule
Reading `await request.form()` inside a `BaseHTTPMiddleware.dispatch()` implementation is safe — the downstream route handler can still read the same form data.

## Why
Starlette 0.37.2 uses `_CachedRequest` (subclass of `Request`) in `BaseHTTPMiddleware`. Its `wrapped_receive` method checks `getattr(self, "_body", None)` — if `body()` was already called by the middleware, it replays `self._body` for the downstream `call_next` receive callable. No double-consume problem.

## How to apply
- Call `await request.form()` in middleware dispatch → body cached in `request._body`
- Call `await call_next(request)` → downstream handler gets the same body via `wrapped_receive`
- This pattern works for Starlette >= 0.37.2; verify if upgrading Starlette major version
