"""
routes/settings.py — Application settings UI: webhooks, scheduler info.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NotificationWebhook
from app.scheduler import get_scheduler

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    webhooks = db.query(NotificationWebhook).order_by(NotificationWebhook.name).all()

    # Scheduler job info
    scheduler = get_scheduler()
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else "N/A"
            jobs.append({"id": job.id, "name": job.name, "next_run": next_run})

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "webhooks": webhooks,
            "scheduler_jobs": jobs,
            "page_title": "Settings",
        },
    )


@router.post("/webhooks/add")
async def webhook_add(
    name: str = Form(...),
    url: str = Form(...),
    on_backup_fail: bool = Form(True),
    on_ping_fail: bool = Form(True),
    db: Session = Depends(get_db),
):
    wh = NotificationWebhook(
        name=name,
        url=url,
        on_backup_fail=on_backup_fail,
        on_ping_fail=on_ping_fail,
    )
    db.add(wh)
    db.commit()
    return RedirectResponse(url="/settings/", status_code=303)


@router.post("/webhooks/{webhook_id}/toggle")
async def webhook_toggle(webhook_id: int, db: Session = Depends(get_db)):
    wh = db.get(NotificationWebhook, webhook_id)
    if wh:
        wh.enabled = not wh.enabled
        db.commit()
    return RedirectResponse(url="/settings/", status_code=303)


@router.post("/webhooks/{webhook_id}/delete")
async def webhook_delete(webhook_id: int, db: Session = Depends(get_db)):
    wh = db.get(NotificationWebhook, webhook_id)
    if wh:
        db.delete(wh)
        db.commit()
    return RedirectResponse(url="/settings/", status_code=303)
