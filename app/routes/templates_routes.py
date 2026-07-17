"""
routes/templates_routes.py — Backup command template CRUD.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.i18n import make_translator
from app.models import BackupTemplate
from app.templating import templates

router = APIRouter(prefix="/templates")


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


@router.get("/", response_class=HTMLResponse)
async def templates_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    tmplates = db.query(BackupTemplate).order_by(BackupTemplate.name).all()
    return templates.TemplateResponse("templates_list.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "templates": tmplates,
        "page_title": "tpl.title",
    })


@router.get("/add", response_class=HTMLResponse)
async def template_add_form(
    request: Request,
    user=Depends(require_auth),
):
    lang = _lang(request)
    return templates.TemplateResponse("template_form.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "template": None,
        "page_title": "tpl.add_title",
    })


@router.post("/add")
async def template_add(
    name: str = Form(...),
    description: str = Form(""),
    device_type: str = Form(""),
    commands: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    tmpl = BackupTemplate(
        name=name,
        description=description,
        device_type=device_type or None,
        commands=commands,
    )
    db.add(tmpl)
    db.commit()
    return RedirectResponse(url="/templates/", status_code=303)


@router.get("/{template_id}/edit", response_class=HTMLResponse)
async def template_edit_form(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    lang = _lang(request)
    tmpl = db.get(BackupTemplate, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return templates.TemplateResponse("template_form.html", {
        "request": request,
        "t": make_translator(lang),
        "lang": lang,
        "theme": request.cookies.get("theme", "dark"),
        "user": user,
        "template": tmpl,
        "page_title": "tpl.edit_title",
    })


@router.post("/{template_id}/edit")
async def template_edit(
    template_id: int,
    name: str = Form(...),
    description: str = Form(""),
    device_type: str = Form(""),
    commands: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    tmpl = db.get(BackupTemplate, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl.name = name
    tmpl.description = description
    tmpl.device_type = device_type or None
    tmpl.commands = commands
    db.commit()
    return RedirectResponse(url="/templates/", status_code=303)


@router.post("/{template_id}/delete")
async def template_delete(
    template_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    tmpl = db.get(BackupTemplate, template_id)
    if tmpl:
        db.delete(tmpl)
        db.commit()
    return RedirectResponse(url="/templates/", status_code=303)
