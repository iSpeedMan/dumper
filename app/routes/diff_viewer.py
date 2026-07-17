"""
routes/diff_viewer.py — Config diff viewer between commits.

Routes:
  GET /diff/{device_id}                  — main view (current config)
  GET /diff/{device_id}/compare          — diff between two commits (?commit_a=&commit_b=)
  GET /diff/{device_id}/view/{sha}       — full config snapshot at a specific commit
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.git_manager import get_git_manager
from app.i18n import make_translator
from app.models import Device
from app.templating import templates

router = APIRouter(prefix="/diff")


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


def _base_ctx(request: Request, user, device: Device, history: list,
              current_config: str, diff_text: str = "", commit_a: str = "",
              commit_b: str = "", active_sha: str = "", view_config=None,
              active_commit=None) -> dict:
    lang = _lang(request)
    return {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "device": device,
        "history": history,
        "current_config": current_config,
        "diff_text": diff_text,
        "commit_a": commit_a,
        "commit_b": commit_b,
        "active_sha": active_sha,
        "view_config": view_config,
        "active_commit": active_commit,
        "page_title": "diff.title",
    }


@router.get("/{device_id}", response_class=HTMLResponse)
async def diff_view(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    group_name = device.group.name if device.group else None
    git_mgr = get_git_manager()
    history = git_mgr.get_commit_history(device.name, group_name, max_count=50)
    current_config = git_mgr.get_latest_config(device.name, group_name) or ""

    return templates.TemplateResponse("diff_viewer.html",
        _base_ctx(request, user, device, history, current_config))


@router.get("/{device_id}/compare", response_class=HTMLResponse)
async def diff_compare(
    device_id: int,
    request: Request,
    commit_a: str = "",
    commit_b: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    group_name = device.group.name if device.group else None
    git_mgr = get_git_manager()
    history = git_mgr.get_commit_history(device.name, group_name, max_count=50)
    current_config = git_mgr.get_latest_config(device.name, group_name) or ""

    diff_text = ""
    if commit_a and commit_b:
        diff_text = git_mgr.get_diff_between_commits(
            device.name, group_name, commit_a, commit_b
        )

    return templates.TemplateResponse("diff_viewer.html",
        _base_ctx(request, user, device, history, current_config,
                  diff_text=diff_text, commit_a=commit_a, commit_b=commit_b))


@router.get("/{device_id}/view/{sha}", response_class=HTMLResponse)
async def diff_view_commit(
    device_id: int,
    sha: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """Show the full config snapshot as it existed at a specific commit."""
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    group_name = device.group.name if device.group else None
    git_mgr = get_git_manager()
    history = git_mgr.get_commit_history(device.name, group_name, max_count=50)
    current_config = git_mgr.get_latest_config(device.name, group_name) or ""

    view_config = git_mgr.get_config_at_commit(device.name, group_name, sha)

    # Find metadata for the active commit
    active_commit = next((c for c in history if c["sha"] == sha), None)

    return templates.TemplateResponse("diff_viewer.html",
        _base_ctx(request, user, device, history, current_config,
                  active_sha=sha, view_config=view_config,
                  active_commit=active_commit))
