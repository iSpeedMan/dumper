"""
routes/inventory.py — Device inventory CRUD + manual backup trigger.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.crypto import encrypt, decrypt
from app.database import get_db
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


@router.get("/", response_class=HTMLResponse)
async def inventory_list(request: Request, db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.name).all()
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "devices": devices,
            "groups": groups,
            "page_title": "Inventory",
        },
    )


@router.get("/add", response_class=HTMLResponse)
async def device_add_form(request: Request, db: Session = Depends(get_db)):
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    tmplates = db.query(BackupTemplate).order_by(BackupTemplate.name).all()
    return templates.TemplateResponse(
        "device_form.html",
        {
            "request": request,
            "device": None,
            "groups": groups,
            "templates": tmplates,
            "netmiko_types": NETMIKO_TYPES,
            "page_title": "Add Device",
        },
    )


@router.post("/add")
async def device_add(
    request: Request,
    db: Session = Depends(get_db),
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
    backup_enabled: bool = Form(True),
    description: str = Form(""),
):
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
        backup_enabled=backup_enabled,
        description=description,
    )
    db.add(device)
    db.commit()
    refresh_custom_device_jobs()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.get("/{device_id}/edit", response_class=HTMLResponse)
async def device_edit_form(device_id: int, request: Request, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    tmplates = db.query(BackupTemplate).order_by(BackupTemplate.name).all()
    # Decrypt for display
    device_data = {
        "id": device.id,
        "name": device.name,
        "hostname": device.hostname,
        "port": device.port,
        "connection_type": device.connection_type.value,
        "netmiko_device_type": device.netmiko_device_type,
        "username": decrypt(device.username),
        "password": "",  # Never pre-fill password
        "enable_secret": "",
        "group_id": device.group_id,
        "template_id": device.template_id,
        "custom_cron": device.custom_cron or "",
        "backup_enabled": device.backup_enabled,
        "description": device.description or "",
    }
    return templates.TemplateResponse(
        "device_form.html",
        {
            "request": request,
            "device": device_data,
            "groups": groups,
            "templates": tmplates,
            "netmiko_types": NETMIKO_TYPES,
            "page_title": f"Edit Device: {device.name}",
        },
    )


@router.post("/{device_id}/edit")
async def device_edit(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
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
    backup_enabled: bool = Form(True),
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
    # Only update password if a new one was provided
    if password:
        device.password = encrypt(password)
    if enable_secret:
        device.enable_secret = encrypt(enable_secret)
    device.group_id = group_id or None
    device.template_id = template_id or None
    device.custom_cron = custom_cron.strip() or None
    device.backup_enabled = backup_enabled
    device.description = description

    db.commit()
    refresh_custom_device_jobs()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.post("/{device_id}/delete")
async def device_delete(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
    refresh_custom_device_jobs()
    return RedirectResponse(url="/inventory/", status_code=303)


@router.post("/{device_id}/backup")
async def device_manual_backup(device_id: int, db: Session = Depends(get_db)):
    """Trigger a manual backup for a single device (runs in background thread)."""
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    import threading
    from app.backup_engine import run_backup_for_device

    thread = threading.Thread(
        target=run_backup_for_device,
        args=(device_id, "manual"),
        daemon=True,
    )
    thread.start()
    return RedirectResponse(url=f"/inventory/", status_code=303)


@router.get("/{device_id}/jobs", response_class=HTMLResponse)
async def device_jobs(device_id: int, request: Request, db: Session = Depends(get_db)):
    """Show backup job history for a device."""
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
    return templates.TemplateResponse(
        "device_jobs.html",
        {
            "request": request,
            "device": device,
            "jobs": jobs,
            "page_title": f"Jobs: {device.name}",
        },
    )


# ---------------------------------------------------------------------------
# Groups CRUD
# ---------------------------------------------------------------------------

@router.get("/groups", response_class=HTMLResponse)
async def groups_list(request: Request, db: Session = Depends(get_db)):
    groups = db.query(DeviceGroup).order_by(DeviceGroup.name).all()
    return templates.TemplateResponse(
        "groups.html",
        {"request": request, "groups": groups, "page_title": "Device Groups"},
    )


@router.post("/groups/add")
async def group_add(
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    group = DeviceGroup(name=name, description=description)
    db.add(group)
    db.commit()
    return RedirectResponse(url="/inventory/groups", status_code=303)


@router.post("/groups/{group_id}/delete")
async def group_delete(group_id: int, db: Session = Depends(get_db)):
    group = db.get(DeviceGroup, group_id)
    if group:
        db.delete(group)
        db.commit()
    return RedirectResponse(url="/inventory/groups", status_code=303)
