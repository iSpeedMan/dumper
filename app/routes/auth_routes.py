"""
routes/auth_routes.py — Login, logout, first-run setup.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_ldap, authenticate_local,
    clear_session, hash_password, set_session_user,
)
from app.database import get_db
from app.models import User
from app.i18n import make_translator
from app.security import brute_force, rate_limiter
from app.templating import templates

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


# ---------------------------------------------------------------------------
# Setup (first run — no users exist)
# ---------------------------------------------------------------------------

@router.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request, db: Session = Depends(get_db)):
    if db.query(User).count() > 0:
        return RedirectResponse(url="/login", status_code=302)
    lang = _get_lang(request)
    return templates.TemplateResponse(request, "setup.html", {        "t": make_translator(lang),
        "lang": lang,
        "error": None,
        "page_title": "setup"})


@router.post("/setup")
async def setup_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User).count() > 0:
        return RedirectResponse(url="/login", status_code=302)

    lang = _get_lang(request)
    if len(password) < 6:
        return templates.TemplateResponse(request, "setup.html", {            "t": make_translator(lang),
            "lang": lang,
            "error": "Пароль должен быть не менее 6 символов" if lang == "ru" else "Password must be at least 6 characters",
            "page_title": "setup"})

    user = User(
        username=username.strip(),
        password_hash=hash_password(password),
        is_admin=True,
        is_active=True,
        is_ldap=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    set_session_user(request, user.id, user.username, is_admin=True)
    logger.info("First admin user '%s' created", username)
    return RedirectResponse(url="/", status_code=302)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, db: Session = Depends(get_db)):
    # Redirect to setup if no users exist
    if db.query(User).count() == 0:
        return RedirectResponse(url="/setup", status_code=302)

    from app.auth import get_session_user
    if get_session_user(request):
        return RedirectResponse(url="/", status_code=302)

    lang = _get_lang(request)
    return templates.TemplateResponse(request, "login.html", {        "t": make_translator(lang),
        "lang": lang,
        "error": None,
        "page_title": "login"})


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    lang = _get_lang(request)
    username = username.strip()

    # ── General rate limit: max 30 login POSTs per minute per IP ──────────
    rate_limiter.check(request, bucket="login", max_requests=30, window_seconds=60)

    # ── Brute-force / fail2ban check ───────────────────────────────────────
    locked, remaining = brute_force.is_locked(request)
    if locked:
        minutes = (remaining + 59) // 60
        error_msg = (
            f"Аккаунт временно заблокирован. Попробуйте через {minutes} мин."
            if lang == "ru"
            else f"Too many failed attempts. Try again in {minutes} min."
        )
        return templates.TemplateResponse(request, "login.html", {            "t": make_translator(lang),
            "lang": lang,
            "error": error_msg,
            "page_title": "login"})

    # 1. Try local DB auth
    user_id = authenticate_local(username, password, db)

    if user_id:
        user = db.get(User, user_id)
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        brute_force.record_success(request)
        set_session_user(request, user_id, username, is_admin=bool(user.is_admin))
        logger.info("Local login: '%s'", username)
        return RedirectResponse(url=next or "/", status_code=302)

    # 2. Try LDAP auth
    ldap_user = authenticate_ldap(username, password, db)
    if ldap_user:
        # Auto-create LDAP user in local DB if not exists
        existing = db.query(User).filter(User.username == username).first()
        if not existing:
            existing = User(
                username=username,
                password_hash=None,
                is_admin=False,
                is_active=True,
                is_ldap=True,
            )
            db.add(existing)
            db.commit()
            db.refresh(existing)
        existing.last_login = datetime.now(timezone.utc)
        db.commit()
        brute_force.record_success(request)
        set_session_user(request, existing.id, username, is_admin=bool(existing.is_admin))
        logger.info("LDAP login: '%s'", username)
        return RedirectResponse(url=next or "/", status_code=302)

    # 3. Failed — record the failure and tell the user how many attempts remain
    brute_force.record_failure(request)
    left = brute_force.remaining_attempts(request)
    logger.warning("Failed login attempt for '%s' (IP left: %d)", username, left)

    if left == 0:
        error_msg = (
            "Аккаунт заблокирован на 5 минут из-за множества неверных попыток."
            if lang == "ru"
            else "Account locked for 5 minutes due to too many failed attempts."
        )
    else:
        error_msg = "auth.wrong_creds"

    return templates.TemplateResponse(request, "login.html", {        "t": make_translator(lang),
        "lang": lang,
        "error": error_msg,
        "page_title": "login"})


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.get("/logout")
async def logout(request: Request):
    clear_session(request)
    return RedirectResponse(url="/login", status_code=302)


# ---------------------------------------------------------------------------
# Language / Theme switch (AJAX-friendly, sets cookies)
# ---------------------------------------------------------------------------

@router.post("/set-lang")
async def set_lang(request: Request, lang: str = Form("ru")):
    resp = RedirectResponse(url=request.headers.get("referer", "/"), status_code=302)
    resp.set_cookie("lang", lang if lang in ("ru", "en") else "ru", max_age=60 * 60 * 24 * 365)
    return resp


@router.post("/set-theme")
async def set_theme(request: Request, theme: str = Form("dark")):
    resp = RedirectResponse(url=request.headers.get("referer", "/"), status_code=302)
    resp.set_cookie("theme", theme if theme in ("dark", "light") else "dark", max_age=60 * 60 * 24 * 365)
    return resp
