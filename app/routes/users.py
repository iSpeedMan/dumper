"""
routes/users.py — User management panel (admin only).

Endpoints:
  GET  /users/                — list all users
  POST /users/add             — create new local user
  POST /users/{id}/role       — toggle admin/readonly
  POST /users/{id}/password   — change password (local users only)
  POST /users/{id}/toggle     — enable/disable account
  POST /users/{id}/delete     — delete user (cannot delete self)
"""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import hash_password, require_auth
from app.database import get_db
from app.i18n import make_translator
from app.models import User
from app.templating import templates

router = APIRouter(prefix="/users")
logger = logging.getLogger(__name__)


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


def _tpl_ctx(request: Request, user: dict, db: Session, extra: dict | None = None):
    """Build common template context."""
    lang = _lang(request)
    ctx = {
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "page_title": "usr.title",
    }
    if extra:
        ctx.update(extra)
    return ctx


def _assert_admin(current_user: dict, db: Session):
    """Raise 403 if the session user is not an admin."""
    db_user = db.get(User, current_user["id"])
    if not db_user or not db_user.is_admin:
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return db_user


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def users_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    _assert_admin(current_user, db)
    lang = _lang(request)

    users = db.query(User).order_by(User.created_at).all()
    flash = request.query_params.get("flash")

    return templates.TemplateResponse(request, "users.html", {
        **_tpl_ctx(request, current_user, db),
        "users": users,
        "current_user_id": current_user["id"],
        "flash": flash})


# ---------------------------------------------------------------------------
# Add local user
# ---------------------------------------------------------------------------

@router.post("/add")
async def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str = Form("off"),       # checkbox sends "on" / absent
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    _assert_admin(current_user, db)

    username = username.strip()
    if not username:
        return RedirectResponse(url="/users/?flash=empty_username", status_code=302)
    if len(password) < 6:
        return RedirectResponse(url="/users/?flash=password_too_short", status_code=302)

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return RedirectResponse(url="/users/?flash=user_exists", status_code=302)

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        is_admin=(is_admin == "on"),
        is_active=True,
        is_ldap=False,
    )
    db.add(new_user)
    db.commit()
    logger.info("User '%s' created by '%s'", username, current_user["username"])
    return RedirectResponse(url="/users/?flash=user_created", status_code=302)


# ---------------------------------------------------------------------------
# Toggle admin role
# ---------------------------------------------------------------------------

@router.post("/{user_id}/role")
async def toggle_role(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    _assert_admin(current_user, db)

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Safety: prevent admin from removing their own admin role
    if target.id == current_user["id"] and target.is_admin:
        return RedirectResponse(url="/users/?flash=cannot_demote_self", status_code=302)

    target.is_admin = not target.is_admin
    db.commit()
    logger.info(
        "Role changed: '%s' is_admin=%s (by '%s')",
        target.username, target.is_admin, current_user["username"],
    )
    return RedirectResponse(url="/users/", status_code=302)


# ---------------------------------------------------------------------------
# Change password (local users only)
# ---------------------------------------------------------------------------

@router.post("/{user_id}/password")
async def change_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    _assert_admin(current_user, db)

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_ldap:
        return RedirectResponse(url="/users/?flash=ldap_no_password", status_code=302)
    if len(new_password) < 6:
        return RedirectResponse(url="/users/?flash=password_too_short", status_code=302)

    target.password_hash = hash_password(new_password)
    db.commit()
    logger.info(
        "Password changed for '%s' by '%s'",
        target.username, current_user["username"],
    )
    return RedirectResponse(url="/users/?flash=password_changed", status_code=302)


# ---------------------------------------------------------------------------
# Enable / disable account
# ---------------------------------------------------------------------------

@router.post("/{user_id}/toggle")
async def toggle_active(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    _assert_admin(current_user, db)

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user["id"]:
        return RedirectResponse(url="/users/?flash=cannot_disable_self", status_code=302)

    target.is_active = not target.is_active
    db.commit()
    logger.info(
        "User '%s' active=%s (by '%s')",
        target.username, target.is_active, current_user["username"],
    )
    return RedirectResponse(url="/users/", status_code=302)


# ---------------------------------------------------------------------------
# Delete user
# ---------------------------------------------------------------------------

@router.post("/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    _assert_admin(current_user, db)

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user["id"]:
        return RedirectResponse(url="/users/?flash=cannot_delete_self", status_code=302)

    username = target.username
    db.delete(target)
    db.commit()
    logger.info("User '%s' deleted by '%s'", username, current_user["username"])
    return RedirectResponse(url="/users/", status_code=302)
