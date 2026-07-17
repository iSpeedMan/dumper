"""
main.py — Dumper application entry point.
"""

import base64
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import _AuthRedirect, auth_redirect_handler
from app.config import settings
from app.database import init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.security import CSRFMiddleware

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.app.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("paramiko").setLevel(logging.WARNING)

logger = logging.getLogger("dumper")


# ---------------------------------------------------------------------------
# Auto-generate master key if missing
# ---------------------------------------------------------------------------

def _ensure_master_key() -> None:
    """
    If encryption.master_key is not set (still CHANGE_ME), generate one
    and save it back to config.yaml so the app can run immediately.
    Logs a prominent warning to remind the admin to back it up.
    """
    if not settings.encryption.master_key.startswith("CHANGE_ME"):
        return  # Already configured

    new_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    settings.encryption.master_key = new_key

    # Patch the cache so crypto.py picks it up
    import app.crypto as _crypto
    _crypto._KEY_CACHE = None  # Force re-derive

    # Write back to config.yaml
    config_path = Path("config.yaml")
    if config_path.exists():
        content = config_path.read_text()
        content = content.replace(
            "master_key: \"CHANGE_ME_base64_encoded_32byte_key\"",
            f'master_key: "{new_key}"',
        )
        config_path.write_text(content)

    logger.warning(
        "⚠  Auto-generated encryption master key: %s\n"
        "   IMPORTANT: Back this up! If lost, all stored credentials are unreadable.\n"
        "   Edit config.yaml to set a permanent key.",
        new_key,
    )


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Dumper v1.0.0")
    _ensure_master_key()
    init_db()
    logger.info("Database initialized")
    _seed_default_templates()
    try:
        start_scheduler()
    except Exception as exc:
        logger.warning("Scheduler startup warning: %s", exc)
    logger.info("Dumper ready — %s:%d", settings.app.host, settings.app.port)
    yield
    stop_scheduler()
    logger.info("Dumper shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Dumper",
    version="1.0.0",
    docs_url="/api/docs" if settings.app.debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Middleware ordering note:
# Starlette applies add_middleware() in REVERSE order — the LAST call becomes
# the OUTERMOST layer (processes requests first).  We need SessionMiddleware to
# run before CSRFMiddleware so the session is populated when CSRF validates it.
#
# Correct execution order on each request:
#   SessionMiddleware → CSRFMiddleware → route handler
#
# To achieve that, add CSRFMiddleware first (inner), then SessionMiddleware (outer).

# Inner: CSRF — checks session token populated by SessionMiddleware above
app.add_middleware(CSRFMiddleware)

# Outer: Session — reads signed cookie and populates request.session
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app.secret_key,
    session_cookie="dumper_session",
    max_age=60 * 60 * 8,   # 8 hours
    https_only=False,       # Set True in production behind HTTPS proxy
    same_site="lax",
)

# Auth redirect exception handler
app.add_exception_handler(_AuthRedirect, auth_redirect_handler)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Routes
from app.routes.auth_routes import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.inventory import router as inventory_router
from app.routes.templates_routes import router as templates_router
from app.routes.diff_viewer import router as diff_router
from app.routes.settings import router as settings_router
from app.routes.users import router as users_router

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(inventory_router)
app.include_router(templates_router)
app.include_router(diff_router)
app.include_router(settings_router)
app.include_router(users_router)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return HTMLResponse(
        "<html><head><meta charset='utf-8'><title>404</title>"
        "<style>body{font-family:sans-serif;background:#000;color:#fff;"
        "display:flex;align-items:center;justify-content:center;"
        "height:100vh;flex-direction:column;gap:1rem;}"
        "a{color:#1283b9;}</style></head>"
        "<body><h1 style='font-size:3rem;font-weight:300'>404</h1>"
        "<p>страница не найдена</p><a href='/'>← на главную</a></body></html>",
        status_code=404,
    )


@app.exception_handler(500)
async def server_error(request: Request, exc):
    logger.exception("Unhandled 500: %s", exc)
    return HTMLResponse(
        "<html><head><meta charset='utf-8'><title>500</title>"
        "<style>body{font-family:sans-serif;background:#000;color:#fff;"
        "display:flex;align-items:center;justify-content:center;"
        "height:100vh;flex-direction:column;gap:1rem;}"
        "a{color:#1283b9;}</style></head>"
        "<body><h1 style='font-size:3rem;font-weight:300'>500</h1>"
        "<p>внутренняя ошибка сервера. проверьте логи.</p>"
        "<a href='/'>← на главную</a></body></html>",
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Default data seeder
# ---------------------------------------------------------------------------

def _seed_default_templates() -> None:
    from app.database import SessionLocal
    from app.models import BackupTemplate
    db = SessionLocal()
    try:
        if db.query(BackupTemplate).count() > 0:
            return
        defaults = [
            BackupTemplate(name="Cisco IOS / IOS-XE", description="Full running-config",
                           device_type="cisco_ios",
                           commands="terminal length 0\nshow running-config\nshow version"),
            BackupTemplate(name="Cisco IOS-XR", device_type="cisco_xr",
                           commands="terminal length 0\nshow running-config\nshow version"),
            BackupTemplate(name="Cisco NX-OS", device_type="cisco_nxos",
                           commands="terminal length 0\nshow running-config\nshow version"),
            BackupTemplate(name="Cisco ASA", device_type="cisco_asa",
                           commands="terminal pager 0\nshow running-config\nshow version"),
            BackupTemplate(name="Juniper JunOS", device_type="juniper_junos",
                           commands="set cli screen-length 0\nshow configuration | no-more\nshow version"),
            BackupTemplate(name="Arista EOS", device_type="arista_eos",
                           commands="terminal length 0\nshow running-config\nshow version"),
            BackupTemplate(name="Huawei VRP", device_type="huawei",
                           commands="screen-length 0 temporary\ndisplay current-configuration\ndisplay version"),
            BackupTemplate(name="MikroTik RouterOS", device_type="mikrotik_routeros",
                           commands="/export\n/system resource print"),
            BackupTemplate(name="HP Comware", device_type="hp_comware",
                           commands="screen-length disable\ndisplay current-configuration\ndisplay version"),
        ]
        for t in defaults:
            db.add(t)
        db.commit()
        logger.info("Seeded %d default backup templates", len(defaults))
    except Exception as exc:
        logger.error("Template seeding failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        workers=1,
        log_level="debug" if settings.app.debug else "info",
        access_log=False,
    )
