"""
routes/settings.py — Settings UI: webhooks, LDAP, scheduler.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.i18n import make_translator
from app.models import AppSetting, NotificationWebhook
from app.scheduler import get_scheduler
from app.templating import templates

router = APIRouter(prefix="/settings")
logger = logging.getLogger(__name__)

LDAP_KEYS = [
    "ldap_enabled", "ldap_server", "ldap_port", "ldap_use_ssl",
    "ldap_base_dn", "ldap_bind_dn", "ldap_bind_password", "ldap_search_filter",
]


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


def _get_settings(db: Session) -> dict:
    rows = db.query(AppSetting).all()
    return {r.key: r.value for r in rows}


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


@router.get("/", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    webhooks = db.query(NotificationWebhook).order_by(NotificationWebhook.name).all()

    scheduler = get_scheduler()
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else "N/A"
            jobs.append({"id": job.id, "name": job.name, "next_run": next_run})

    app_settings = _get_settings(db)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "webhooks": webhooks,
        "scheduler_jobs": jobs,
        "app_settings": app_settings,
        "page_title": "set.title",
    })


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

@router.post("/webhooks/add")
async def webhook_add(
    name: str = Form(...),
    url: str = Form(...),
    on_backup_fail: Optional[str] = Form(None),
    on_ping_fail: Optional[str] = Form(None),
    send_diff: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    wh = NotificationWebhook(
        name=name,
        url=url,
        on_backup_fail=on_backup_fail == "true",
        on_ping_fail=on_ping_fail == "true",
        send_diff=send_diff == "true",
    )
    db.add(wh)
    db.commit()
    return RedirectResponse(url="/settings/", status_code=303)


@router.post("/webhooks/{webhook_id}/toggle")
async def webhook_toggle(
    webhook_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    wh = db.get(NotificationWebhook, webhook_id)
    if wh:
        wh.enabled = not wh.enabled
        db.commit()
    return RedirectResponse(url="/settings/", status_code=303)


@router.post("/webhooks/{webhook_id}/delete")
async def webhook_delete(
    webhook_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    wh = db.get(NotificationWebhook, webhook_id)
    if wh:
        db.delete(wh)
        db.commit()
    return RedirectResponse(url="/settings/", status_code=303)


# ---------------------------------------------------------------------------
# LDAP settings
# ---------------------------------------------------------------------------

@router.post("/ldap/save")
async def ldap_save(
    request: Request,
    ldap_enabled: Optional[str] = Form(None),
    ldap_server: str = Form(""),
    ldap_port: str = Form("389"),
    ldap_use_ssl: Optional[str] = Form(None),
    ldap_base_dn: str = Form(""),
    ldap_bind_dn: str = Form(""),
    ldap_bind_password: str = Form(""),
    ldap_search_filter: str = Form("(sAMAccountName={username})"),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    values = {
        "ldap_enabled": "true" if ldap_enabled == "true" else "false",
        "ldap_server": ldap_server,
        "ldap_port": ldap_port or "389",
        "ldap_use_ssl": "true" if ldap_use_ssl == "true" else "false",
        "ldap_base_dn": ldap_base_dn,
        "ldap_bind_dn": ldap_bind_dn,
        "ldap_bind_password": ldap_bind_password,
        "ldap_search_filter": ldap_search_filter or "(sAMAccountName={username})",
    }
    for k, v in values.items():
        _set_setting(db, k, v)
    db.commit()
    return RedirectResponse(url="/settings/", status_code=303)


@router.post("/ldap/test")
async def ldap_test(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """Test LDAP bind with service account and return JSON result."""
    app_settings = _get_settings(db)
    server_host = app_settings.get("ldap_server", "")
    port = int(app_settings.get("ldap_port", "389"))
    use_ssl = app_settings.get("ldap_use_ssl", "false") == "true"
    bind_dn = app_settings.get("ldap_bind_dn", "")
    bind_password = app_settings.get("ldap_bind_password", "")

    if not server_host:
        return JSONResponse({"ok": False, "message": "LDAP server not configured"})

    try:
        import ldap3
        server = ldap3.Server(server_host, port=port, use_ssl=use_ssl,
                               get_info=ldap3.NONE, connect_timeout=5)
        if bind_dn and bind_password:
            conn = ldap3.Connection(server, bind_dn, bind_password, auto_bind=True)
            conn.unbind()
            return JSONResponse({"ok": True, "message": f"Connected to {server_host}:{port} successfully"})
        else:
            conn = ldap3.Connection(server, auto_bind=True)
            conn.unbind()
            return JSONResponse({"ok": True, "message": f"Anonymous bind to {server_host}:{port} OK"})
    except Exception as exc:
        logger.warning("LDAP test failed: %s", exc)
        return JSONResponse({"ok": False, "message": str(exc)})

