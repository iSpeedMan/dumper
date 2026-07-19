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
from app.scheduler import get_scheduler, reschedule_default_backup, _get_default_cron_from_db
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
            # Pass datetime object directly — fmt_dt filter handles formatting
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time,  # datetime | None
            })

    app_settings = _get_settings(db)
    backup_cron = app_settings.get("backup_cron") or _get_default_cron_from_db()

    from app.retention import DEFAULT_RETENTION_DAYS
    try:
        retention_days = int(app_settings.get("retention_days", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        retention_days = DEFAULT_RETENTION_DAYS

    return templates.TemplateResponse(request, "settings.html", {
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "webhooks": webhooks,
        "scheduler_jobs": jobs,
        "app_settings": app_settings,
        "backup_cron": backup_cron,
        "retention_days": retention_days,
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


# ---------------------------------------------------------------------------
# Scheduler settings
# ---------------------------------------------------------------------------

@router.post("/scheduler/save")
async def scheduler_save(
    request: Request,
    backup_cron: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """Save the default backup cron expression and immediately reschedule the job."""
    backup_cron = backup_cron.strip()
    # Validate: must be exactly 5 whitespace-separated fields
    parts = backup_cron.split()
    if len(parts) != 5:
        lang = _lang(request)
        webhooks = db.query(NotificationWebhook).order_by(NotificationWebhook.name).all()
        scheduler = get_scheduler()
        jobs = []
        if scheduler.running:
            for job in scheduler.get_jobs():
                jobs.append({"id": job.id, "name": job.name, "next_run": job.next_run_time})
        app_settings = _get_settings(db)
        from app.i18n import make_translator
        return templates.TemplateResponse(
            request, "settings.html",
            {
                "t": make_translator(lang),
                "lang": lang,
                "theme": request.cookies.get("theme", "dark"),
                "user": user,
                "webhooks": webhooks,
                "scheduler_jobs": jobs,
                "app_settings": app_settings,
                "backup_cron": backup_cron,
                "cron_error": True,
                "page_title": "set.title",
            },
            status_code=422,
        )

    _set_setting(db, "backup_cron", backup_cron)
    db.commit()

    try:
        reschedule_default_backup(backup_cron)
    except Exception as exc:
        logger.error("Failed to reschedule default backup: %s", exc)

    return RedirectResponse(url="/settings/", status_code=303)


@router.post("/retention/save")
async def retention_save(
    request: Request,
    retention_days: int = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """Save global backup retention period."""
    if retention_days < 1:
        retention_days = 1
    _set_setting(db, "retention_days", str(retention_days))
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

