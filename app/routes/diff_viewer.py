"""
routes/diff_viewer.py — Config diff viewer between commits.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.git_manager import get_git_manager
from app.models import BackupJob, Device

router = APIRouter(prefix="/diff")
templates = Jinja2Templates(directory="templates")


@router.get("/{device_id}", response_class=HTMLResponse)
async def diff_view(device_id: int, request: Request, db: Session = Depends(get_db)):
    """Show commit history for a device and allow comparing two commits."""
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    group_name = device.group.name if device.group else None
    git_mgr = get_git_manager()
    history = git_mgr.get_commit_history(device.name, group_name, max_count=30)
    current_config = git_mgr.get_latest_config(device.name, group_name)

    return templates.TemplateResponse(
        "diff_viewer.html",
        {
            "request": request,
            "device": device,
            "history": history,
            "current_config": current_config or "",
            "diff_text": "",
            "commit_a": "",
            "commit_b": "",
            "page_title": f"Diff Viewer: {device.name}",
        },
    )


@router.get("/{device_id}/compare", response_class=HTMLResponse)
async def diff_compare(
    device_id: int,
    request: Request,
    commit_a: str = "",
    commit_b: str = "",
    db: Session = Depends(get_db),
):
    """Compare two commits for a device."""
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    group_name = device.group.name if device.group else None
    git_mgr = get_git_manager()
    history = git_mgr.get_commit_history(device.name, group_name, max_count=30)
    current_config = git_mgr.get_latest_config(device.name, group_name)

    diff_text = ""
    if commit_a and commit_b:
        diff_text = git_mgr.get_diff_between_commits(
            device.name, group_name, commit_a, commit_b
        )

    return templates.TemplateResponse(
        "diff_viewer.html",
        {
            "request": request,
            "device": device,
            "history": history,
            "current_config": current_config or "",
            "diff_text": diff_text,
            "commit_a": commit_a,
            "commit_b": commit_b,
            "page_title": f"Diff Viewer: {device.name}",
        },
    )
