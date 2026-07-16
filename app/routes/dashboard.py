"""
routes/dashboard.py — Main dashboard: device availability overview, recent jobs.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BackupJob, BackupJobStatus, Device, DeviceStatus, PingStatus

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Main dashboard page."""
    # Device counts by status
    total_devices = db.query(func.count(Device.id)).scalar() or 0
    online_count = (
        db.query(func.count(Device.id))
        .filter(Device.status == DeviceStatus.ONLINE)
        .scalar() or 0
    )
    offline_count = (
        db.query(func.count(Device.id))
        .filter(Device.status == DeviceStatus.OFFLINE)
        .scalar() or 0
    )
    unknown_count = total_devices - online_count - offline_count

    # Recent backup jobs (last 20)
    recent_jobs = (
        db.query(BackupJob)
        .join(Device)
        .order_by(BackupJob.started_at.desc())
        .limit(20)
        .all()
    )

    # Last 24h backup stats
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    jobs_24h = db.query(BackupJob).filter(BackupJob.started_at >= since).all()
    success_24h = sum(1 for j in jobs_24h if j.status == BackupJobStatus.SUCCESS)
    failed_24h = sum(1 for j in jobs_24h if j.status == BackupJobStatus.FAILED)

    # Device table (with ping status)
    devices = (
        db.query(Device)
        .order_by(Device.status, Device.name)
        .limit(100)
        .all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_devices": total_devices,
            "online_count": online_count,
            "offline_count": offline_count,
            "unknown_count": unknown_count,
            "recent_jobs": recent_jobs,
            "success_24h": success_24h,
            "failed_24h": failed_24h,
            "devices": devices,
            "page_title": "Dashboard",
        },
    )


@router.get("/api/stats")
async def api_stats(db: Session = Depends(get_db)):
    """JSON endpoint for live dashboard stats (used by auto-refresh JS)."""
    total = db.query(func.count(Device.id)).scalar() or 0
    online = (
        db.query(func.count(Device.id))
        .filter(Device.status == DeviceStatus.ONLINE)
        .scalar() or 0
    )
    offline = (
        db.query(func.count(Device.id))
        .filter(Device.status == DeviceStatus.OFFLINE)
        .scalar() or 0
    )
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
