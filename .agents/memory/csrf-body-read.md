---
name: CSRF middleware body reading in BaseHTTPMiddleware
description: Starlette 0.37 _CachedRequest.wrapped_receive replays self._body; safe to call request.form() in BaseHTTPMiddleware before call_next.
---

# CSRF Middleware Body Reading

## Rule
Always call `await request.body()` BEFORE `await request.form()` in a `BaseHTTPMiddleware.dispatch()` implementation — then the route handler can still read the same form data.

## Why
Starlette 0.37.2 uses `_CachedRequest` in `BaseHTTPMiddleware`. Its `wrapped_receive` checks `getattr(self, "_body", None)` and replays the cached body to downstream handlers — BUT only if `_body` was set via `request.body()`. Calling `form()` directly reads via `stream()`, sets `_stream_consumed=True` WITHOUT setting `_body`, so `wrapped_receive` sends an empty body downstream → route handler gets 422 (missing form fields).

## How to apply
- Call `await request.form()` in middleware dispatch → body cached in `request._body`
- Call `await call_next(request)` → downstream handler gets the same body via `wrapped_receive`
- This pattern works for Starlette >= 0.37.2; verify if upgrading Starlette major version
