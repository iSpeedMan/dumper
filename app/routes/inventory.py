"""
routes/inventory.py — Device inventory CRUD + manual backup trigger.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.crypto import encrypt, decrypt
from app.database import get_db
from app.i18n import make_translator
from app.models import BackupJob, BackupJobStatus, BackupTemplate, Device, DeviceGroup
from app.scheduler import refresh_custom_device_jobs

router = APIRouter(prefix="/inventory")
templates = Jinja2Templates(directory="templates")

NETMIKO_TYPES = [
    "cisco_ios", "cisco_xr", "cisco_nxos", "cisco_asa", "cisco_wlc",
    "juniper_junos", "arista_eos", "huawei", "huawei_vrpv8",
    "hp_comware", "hp_procurve", "mikrotik_routeros",
    "linux", "generic", "autodetect",
]


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


def _last_config_dates(device_ids: list, db: Session) -> dict:
    """Return {device_id: finished_at} for the last successful backup per device."""
    if not device_ids:
        return {}
    from sqlalchemy import func
    subq = (
        db.query(
            BackupJob.device_id,
            func.max(BackupJob.finished_at).label("last_date")
        )
        .filter(
            BackupJob.device_id.in_(device_ids),
            BackupJob.status == BackupJobStatus.SUCCESS,
        )
        .group_by(BackupJob.device_id)
        .subquery()
    )
    rows = db.query(subq).all()
    return {row.device_id: row.last_date for row in rows}


@router.get("/", response_class=HTMLResponse)
async def inventory_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    devices = db.query(Device).order_by(Device.name).all()
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    last_dates = _last_config_dates([d.id for d in devices], db)
    return templates.TemplateResponse("inventory.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "devices": devices,
        "groups": groups,
        "last_dates": last_dates,
        "page_title": "inventory",
    })


@router.get("/add", response_class=HTMLResponse)
async def device_add_form(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    tmplates = db.query(BackupTemplate).order_by(BackupTemplate.name).all()
    return templates.TemplateResponse("device_form.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "device": None,
        "groups": groups,
        "templates": tmplates,
        "netmiko_types": NETMIKO_TYPES,
        "page_title": "dev.add_title",
    })


@router.post("/add")
async def device_add(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
    name: str = Form(...),
    hostname: str = Form(...),
    port: int = Form(22),
    connection_type: str = Form("ssh"),
    netmiko_device_type: str = Form("cisco_ios"),
    username: str = Form(...),
    password: str = Form(...),
    enable_secret: str = Form(""),
    group_id: Optional[int] = Form(None),
    template_id: Optional[int] = Form(None),
    custom_cron: str = Form(""),
    backup_enabled: Optional[str] = Form(None),
    description: str = Form(""),
):
    from app.crypto import encrypt
    device = Device(
        name=name,
        hostname=hostname,
        port=port,
        connection_type=connection_type,
        netmiko_device_type=netmiko_device_type,
        username=encrypt(username),
        password=encrypt(password),
        enable_secret=encrypt(enable_secret) if enable_secret else None,
        group_id=group_id or None,
        template_id=template_id or None,
        custom_cron=custom_cron.strip() or None,
        backup_enabled=backup_enabled == "true",
        description=description,
    )
    db.add(device)
    db.commit()
    refresh_custom_device_jobs()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.get("/{device_id}/edit", response_class=HTMLResponse)
async def device_edit_form(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    tmplates = db.query(BackupTemplate).order_by(BackupTemplate.name).all()

    # Decrypt username — if master key not configured, show placeholder
    try:
        plain_username = decrypt(device.username)
    except (RuntimeError, ValueError):
        plain_username = "*** key not configured ***"

    device_data = {
        "id": device.id,
        "name": device.name,
        "hostname": device.hostname,
        "port": device.port,
        "connection_type": device.connection_type.value,
        "netmiko_device_type": device.netmiko_device_type,
        "username": plain_username,
        "password": "",
        "enable_secret": "",
        "group_id": device.group_id,
        "template_id": device.template_id,
        "custom_cron": device.custom_cron or "",
        "backup_enabled": device.backup_enabled,
        "description": device.description or "",
    }
    return templates.TemplateResponse("device_form.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "device": device_data,
        "groups": groups,
        "templates": tmplates,
        "netmiko_types": NETMIKO_TYPES,
        "page_title": "dev.edit_title",
    })


@router.post("/{device_id}/edit")
async def device_edit(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
    name: str = Form(...),
    hostname: str = Form(...),
    port: int = Form(22),
    connection_type: str = Form("ssh"),
    netmiko_device_type: str = Form("cisco_ios"),
    username: str = Form(...),
    password: str = Form(""),
    enable_secret: str = Form(""),
    group_id: Optional[int] = Form(None),
    template_id: Optional[int] = Form(None),
    custom_cron: str = Form(""),
    backup_enabled: Optional[str] = Form(None),
    description: str = Form(""),
):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.name = name
    device.hostname = hostname
    device.port = port
    device.connection_type = connection_type
    device.netmiko_device_type = netmiko_device_type
    device.username = encrypt(username)
    if password:
        device.password = encrypt(password)
    if enable_secret:
        device.enable_secret = encrypt(enable_secret)
    device.group_id = group_id or None
    device.template_id = template_id or None
    device.custom_cron = custom_cron.strip() or None
    device.backup_enabled = backup_enabled == "true"
    device.description = description

    db.commit()
    refresh_custom_device_jobs()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.post("/{device_id}/delete")
async def device_delete(
    device_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
    refresh_custom_device_jobs()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.post("/{device_id}/backup")
async def device_manual_backup(
    device_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    import threading
    from app.backup_engine import run_backup_for_device
    threading.Thread(target=run_backup_for_device, args=(device_id, "manual"), daemon=True).start()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.get("/{device_id}/jobs", response_class=HTMLResponse)
async def device_jobs(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    jobs = (
        db.query(BackupJob)
        .filter(BackupJob.device_id == device_id)
        .order_by(BackupJob.started_at.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse("device_jobs.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "device": device,
        "jobs": jobs,
        "page_title": "job.title",
    })


# --- Groups ---

@router.get("/groups", response_class=HTMLResponse)
async def groups_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    return templates.TemplateResponse("groups.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "groups": groups,
        "page_title": "grp.title",
    })


@router.post("/groups/add")
async def group_add(
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    group = DeviceGroup(name=name, description=description)
    db.add(group)
    db.commit()
    return RedirectResponse(url="/inventory/groups", status_code=303)


@router.post("/groups/{group_id}/delete")
async def group_delete(
    group_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    group = db.get(DeviceGroup, group_id)
    if group:
        db.delete(group)
        db.commit()
    return RedirectResponse(url="/inventory/groups", status_code=303)
