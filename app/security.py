"""
security.py — Security middleware and utilities for Dumper.

Provides:
  1. BruteForceProtection  — in-memory fail2ban-like lockout for /login
                             (5 wrong attempts → 5 min ban per IP)
  2. RateLimiter           — simple sliding-window rate limiter per IP
  3. CSRFMiddleware        — session-bound CSRF tokens checked on
                             POST / PUT / DELETE requests
  4. Helper: csrf_token(request) — return (and create) the token for a request

Usage in main.py:
    from app.security import BruteForceProtection, CSRFMiddleware, rate_limiter
    app.add_middleware(CSRFMiddleware)
    # rate_limiter used as a FastAPI dependency
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from typing import Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Brute-force / fail2ban protection for login
# ============================================================================

class BruteForceProtection:
    """
    Per-IP login attempt tracker with automatic lockout.

    Defaults: 5 failed attempts → locked for 300 seconds (5 minutes).
    Thread-safe for the single-process, single-worker Uvicorn setup used
    by Dumper.  If you switch to multi-worker, move state to Redis.
    """

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        # ip → list of failure timestamps (float)
        self._failures: dict[str, list[float]] = defaultdict(list)
        # ip → lockout-expiry timestamp (float); absent means not locked
        self._lockouts: dict[str, float] = {}

    def _get_ip(self, request: Request) -> str:
        """Extract the real client IP from X-Real-IP (set by nginx proxy_set_header
        X-Real-IP $remote_addr) which cannot be spoofed by the client.
        Falls back to the TCP peer address."""
        # X-Real-IP is set by nginx to $remote_addr (the actual TCP peer);
        # it is NOT client-controlled.  Avoid X-Forwarded-For — its first value
        # can be injected by the client to bypass per-IP rate limits/lockouts.
        xri = request.headers.get("X-Real-IP")
        if xri:
            return xri.strip()
        return request.client.host if request.client else "unknown"

    def is_locked(self, request: Request) -> tuple[bool, int]:
        """
        Check whether the IP is currently locked out.

        Returns:
            (locked: bool, seconds_remaining: int)
        """
        ip = self._get_ip(request)
        expiry = self._lockouts.get(ip)
        if expiry and time.time() < expiry:
            remaining = int(expiry - time.time())
            return True, remaining
        # Lockout expired — clean up
        if expiry:
            del self._lockouts[ip]
            self._failures.pop(ip, None)
        return False, 0

    def record_failure(self, request: Request) -> None:
        """Record a failed login attempt and lock the IP if threshold exceeded."""
        ip = self._get_ip(request)
        now = time.time()

        # Evict attempts older than the lockout window
        cutoff = now - self.lockout_seconds
        self._failures[ip] = [t for t in self._failures[ip] if t > cutoff]

        self._failures[ip].append(now)
        count = len(self._failures[ip])

        if count >= self.max_attempts:
            self._lockouts[ip] = now + self.lockout_seconds
            logger.warning(
                "BruteForce: IP %s locked out for %ds after %d failed attempts",
                ip, self.lockout_seconds, count,
            )

    def record_success(self, request: Request) -> None:
        """Clear failure history on successful login."""
        ip = self._get_ip(request)
        self._failures.pop(ip, None)
        self._lockouts.pop(ip, None)

    def remaining_attempts(self, request: Request) -> int:
        """Return how many login attempts the IP has left before lockout."""
        ip = self._get_ip(request)
        now = time.time()
        cutoff = now - self.lockout_seconds
        recent = [t for t in self._failures.get(ip, []) if t > cutoff]
        return max(0, self.max_attempts - len(recent))


# Singleton used across the app
brute_force = BruteForceProtection(max_attempts=5, lockout_seconds=300)


# ============================================================================
# 2. Simple rate limiter (sliding window, per IP)
# ============================================================================

class _RateLimiter:
    """
    Sliding-window rate limiter.

    Each (ip, bucket) pair gets its own counter.  Buckets let you apply
    different limits to different route groups.
    """

    def __init__(self) -> None:
        # (ip, bucket) → deque of request timestamps
        self._windows: dict[tuple[str, str], deque] = defaultdict(deque)

    def _get_ip(self, request: Request) -> str:
        """Use X-Real-IP (set by nginx $remote_addr) — not spoofable by clients."""
        xri = request.headers.get("X-Real-IP")
        if xri:
            return xri.strip()
        return request.client.host if request.client else "unknown"

    def check(
        self,
        request: Request,
        *,
        bucket: str = "global",
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        """
        Raise HTTP 429 if the IP has exceeded max_requests in window_seconds.
        Call this as a FastAPI dependency or manually in a route handler.
        """
        ip = self._get_ip(request)
        key = (ip, bucket)
        now = time.time()
        cutoff = now - window_seconds
        dq = self._windows[key]

        # Evict old entries
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= max_requests:
            logger.warning("RateLimit: IP %s exceeded %d req/%ds [%s]",
                           ip, max_requests, window_seconds, bucket)
            raise HTTPException(
                status_code=429,
                detail="Слишком много запросов. Попробуйте позже.",
            )

        dq.append(now)


rate_limiter = _RateLimiter()


# ============================================================================
# 3. CSRF protection middleware
# ============================================================================

# Routes that are exempt from CSRF (webhooks from external systems, API endpoints
# consumed by machine clients that set their own auth headers, etc.)
_CSRF_EXEMPT_PATHS = {
    "/set-lang",   # idempotent cookie setter
    "/set-theme",  # idempotent cookie setter
}

# Header or form field name
CSRF_TOKEN_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
_CSRF_SESSION_KEY = "_csrf_token"
_UNSAFE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def csrf_token(request: Request) -> str:
    """
    Return the CSRF token for this session, creating it if missing.
    Expose this in Jinja2 globals so every template can call {{ csrf_token() }}.
    """
    token = request.session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        request.session[_CSRF_SESSION_KEY] = token
    return token


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using the Synchronizer Token Pattern.

    - On any unsafe HTTP method (POST / PUT / DELETE / PATCH):
      the token must be present either in the form body (field "csrf_token")
      or in the request header "X-CSRF-Token".
    - The token is bound to the session; it is created lazily on the first
      GET request that touches the session.
    - Requests without a session (unauthenticated) still pass — the login
      form itself carries the CSRF token once the GET is served.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in _UNSAFE_METHODS and request.url.path not in _CSRF_EXEMPT_PATHS:
            await self._verify(request)
        return await call_next(request)

    async def _verify(self, request: Request) -> None:
        session_token = request.session.get(_CSRF_SESSION_KEY)

        # Try header first (for AJAX), then form body
        submitted = request.headers.get(CSRF_HEADER)
        if not submitted:
            # IMPORTANT: call request.body() BEFORE request.form().
            # Starlette's _CachedRequest.wrapped_receive only replays the body
            # to downstream handlers when self._body is set (i.e. body() was called).
            # form() reads from stream() which marks _stream_consumed=True but does NOT
            # set _body — so wrapped_receive would send an empty body to the route handler.
            # Calling body() first caches the raw bytes; then form() yields from _body.
            try:
                await request.body()          # ensures _body is cached
                form = await request.form()   # now reads safely from _body via stream()
                submitted = form.get(CSRF_TOKEN_FIELD, "")
            except Exception:
                submitted = ""

        # Reject if either token is absent or they don't match.
        # We no longer skip validation when session_token is missing — a legitimate
        # form submission always has the token (created during the GET that served
        # the form).  A direct cross-site POST with no session carries no token and
        # must be rejected, including the unauthenticated /setup endpoint.
        if not session_token or not submitted or not hmac.compare_digest(submitted, session_token):
            logger.warning(
                "CSRF check failed for %s %s (token missing or mismatch)",
                request.method, request.url.path,
            )
            raise HTTPException(status_code=403, detail="CSRF token недействителен.")
