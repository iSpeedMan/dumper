"""
routes/dashboard.py — Main dashboard.
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.i18n import make_translator
from app.models import BackupJob, BackupJobStatus, Device, DeviceStatus
from app.templating import templates

router = APIRouter()


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    total_devices = db.query(func.count(Device.id)).scalar() or 0
    online_count = db.query(func.count(Device.id)).filter(Device.status == DeviceStatus.ONLINE).scalar() or 0
    offline_count = db.query(func.count(Device.id)).filter(Device.status == DeviceStatus.OFFLINE).scalar() or 0
    unknown_count = total_devices - online_count - offline_count

    recent_jobs = (
        db.query(BackupJob)
        .join(Device)
        .order_by(BackupJob.started_at.desc())
        .limit(20)
        .all()
    )

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    jobs_24h = db.query(BackupJob).filter(BackupJob.started_at >= since).all()
    success_24h = sum(1 for j in jobs_24h if j.status == BackupJobStatus.SUCCESS)
    failed_24h = sum(1 for j in jobs_24h if j.status == BackupJobStatus.FAILED)

    devices = db.query(Device).order_by(Device.status, Device.name).limit(100).all()

    return templates.TemplateResponse(request, "dashboard.html", {        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "total_devices": total_devices,
        "online_count": online_count,
        "offline_count": offline_count,
        "unknown_count": unknown_count,
        "recent_jobs": recent_jobs,
        "success_24h": success_24h,
        "failed_24h": failed_24h,
        "devices": devices,
        "page_title": "dash.title"})


@router.get("/api/stats")
async def api_stats(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    total = db.query(func.count(Device.id)).scalar() or 0
    online = db.query(func.count(Device.id)).filter(Device.status == DeviceStatus.ONLINE).scalar() or 0
    offline = db.query(func.count(Device.id)).filter(Device.status == DeviceStatus.OFFLINE).scalar() or 0
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    jobs_24h = db.query(BackupJob).filter(BackupJob.started_at >= since).all()

    return {
        "total": total,
        "online": online,
        "offline": offline,
        "unknown": total - online - offline,
        "success_24h": sum(1 for j in jobs_24h if j.status == BackupJobStatus.SUCCESS),
        "failed_24h": sum(1 for j in jobs_24h if j.status == BackupJobStatus.FAILED),
    }
