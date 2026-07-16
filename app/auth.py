"""
auth.py — Authentication utilities.

Supports:
  1. Local users (bcrypt hashed passwords in SQLite)
  2. LDAP authentication (configurable from settings UI)

Session stored in signed cookie via Starlette SessionMiddleware.
FastAPI dependency `require_auth` redirects to /login if not authenticated.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def set_session_user(request: Request, user_id: int, username: str) -> None:
    request.session["user_id"] = user_id
    request.session["username"] = username


def clear_session(request: Request) -> None:
    request.session.clear()


def get_session_user(request: Request) -> Optional[dict]:
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    if user_id and username:
        return {"id": user_id, "username": username}
    return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def require_auth(request: Request):
    """
    Dependency: ensures the user is authenticated.
    Redirects to /login for GET requests, raises 401 for API requests.
    """
    user = get_session_user(request)
    if user is None:
        # Check if this is an API call (accept: application/json)
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            raise HTTPException(status_code=401, detail="Not authenticated")
        # Redirect to login preserving the target URL
        next_url = str(request.url)
        raise _AuthRedirect(f"/login?next={next_url}")
    return user


class _AuthRedirect(Exception):
    """Internal exception to trigger a login redirect."""
    def __init__(self, url: str):
        self.url = url


async def auth_redirect_handler(request: Request, exc: _AuthRedirect):
    return RedirectResponse(url=exc.url, status_code=302)


def get_current_user_optional(request: Request) -> Optional[dict]:
    """Like require_auth but returns None instead of redirecting."""
    return get_session_user(request)


# ---------------------------------------------------------------------------
# Local DB authentication
# ---------------------------------------------------------------------------

def authenticate_local(username: str, password: str, db: Session) -> Optional[int]:
    """
    Verify username/password against the local User table.
    Returns user_id on success, None on failure.
    """
    from app.models import User
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user.id


# ---------------------------------------------------------------------------
# LDAP authentication
# ---------------------------------------------------------------------------

def authenticate_ldap(username: str, password: str, db: Session) -> Optional[str]:
    """
    Authenticate a user against LDAP using stored settings.
    Returns the username on success, None on failure.

    Uses ldap3 library (pure Python, no C extensions).
    """
    from app.models import AppSetting
    import ldap3

    def _setting(key: str, default: str = "") -> str:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else default

    enabled = _setting("ldap_enabled", "false").lower() == "true"
    if not enabled:
        return None

    server_host = _setting("ldap_server")
    port = int(_setting("ldap_port", "389"))
    use_ssl = _setting("ldap_use_ssl", "false").lower() == "true"
    base_dn = _setting("ldap_base_dn")
    bind_dn = _setting("ldap_bind_dn")
    bind_password = _setting("ldap_bind_password")
    search_filter = _setting("ldap_search_filter", "(sAMAccountName={username})")

    if not server_host or not base_dn:
        logger.warning("LDAP not fully configured — skipping LDAP auth")
        return None

    try:
        server = ldap3.Server(
            server_host,
            port=port,
            use_ssl=use_ssl,
            get_info=ldap3.NONE,
            connect_timeout=5,
        )

        # Step 1: bind with service account to find the user's DN
        if bind_dn and bind_password:
            conn = ldap3.Connection(server, bind_dn, bind_password, auto_bind=True)
            filt = search_filter.replace("{username}", ldap3.utils.dn.escape_rdn(username))
            conn.search(base_dn, filt, attributes=["distinguishedName", "sAMAccountName"])
            if not conn.entries:
                logger.info("LDAP: user '%s' not found", username)
                return None
            user_dn = conn.entries[0].entry_dn
            conn.unbind()
        else:
            # Simple bind: construct DN directly
            user_dn = search_filter.replace("{username}", username) + "," + base_dn

        # Step 2: bind as the user with their password
        user_conn = ldap3.Connection(server, user_dn, password, auto_bind=True)
        user_conn.unbind()
        logger.info("LDAP authentication success for '%s'", username)
        return username

    except ldap3.core.exceptions.LDAPBindError:
        logger.info("LDAP authentication failed for '%s' (bad credentials)", username)
        return None
    except Exception as exc:
        logger.error("LDAP authentication error for '%s': %s", username, exc)
        return None
