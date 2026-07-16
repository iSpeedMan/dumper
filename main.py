"""
main.py — Dumper application entry point.

Starts a FastAPI app with:
  - Jinja2 SSR templates
  - SQLite database (auto-initialized on startup)
  - APScheduler background jobs (ping sweep + backup cron)
  - Static file serving

Usage:
  python main.py
  uvicorn main:app --host 0.0.0.0 --port 5000 --workers 1

Production (systemd): see dumper.service
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db
from app.scheduler import start_scheduler, stop_scheduler

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.app.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

# Reduce verbosity of noisy libraries
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if settings.app.debug else logging.WARNING
)
logging.getLogger("paramiko").setLevel(logging.WARNING)

logger = logging.getLogger("dumper")


# ---------------------------------------------------------------------------
# App lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    - Runs startup logic before 'yield'
    - Runs shutdown logic after 'yield'
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Starting Dumper v1.0.0")
    logger.info("Database: %s", settings.database.path)
    logger.info("Git repo: %s", settings.git.repo_path)

    # Initialize database tables
    init_db()
    logger.info("Database initialized")

    # Seed default backup templates if DB is empty
    _seed_default_templates()

    # Start background scheduler (ping + backup jobs)
    try:
        start_scheduler()
    except Exception as exc:
        logger.warning("Scheduler startup warning: %s", exc)

    logger.info("Dumper is ready — listening on %s:%d", settings.app.host, settings.app.port)

    yield  # App is running

    # ── Shutdown ─────────────────────────────────────────────────────────────
    stop_scheduler()
    logger.info("Dumper shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Dumper",
    description="Network configuration backup manager",
    version="1.0.0",
    docs_url="/api/docs" if settings.app.debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register route blueprints
from app.routes.dashboard import router as dashboard_router
from app.routes.inventory import router as inventory_router
from app.routes.templates_routes import router as templates_router
from app.routes.diff_viewer import router as diff_router
from app.routes.settings import router as settings_router

app.include_router(dashboard_router)
app.include_router(inventory_router)
app.include_router(templates_router)
app.include_router(diff_router)
app.include_router(settings_router)

# ---------------------------------------------------------------------------
# 404 handler
# ---------------------------------------------------------------------------

_jinja_templates = Jinja2Templates(directory="templates")


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return HTMLResponse(
        content=f"""
        <html><head><meta charset="utf-8"><title>404 — Dumper</title>
        <style>body{{font-family:sans-serif;background:#0f1117;color:#e2e8f0;display:flex;
        align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:1rem;}}
        a{{color:#4f8ef7;}}</style></head>
        <body><h1>404</h1><p>Страница не найдена.</p><a href="/">← На главную</a></body></html>
        """,
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.exception("Unhandled 500 error: %s", exc)
    return HTMLResponse(
        content="""
        <html><head><meta charset="utf-8"><title>500 — Dumper</title>
        <style>body{{font-family:sans-serif;background:#0f1117;color:#e2e8f0;display:flex;
        align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:1rem;}}
        a{{color:#4f8ef7;}}</style></head>
        <body><h1>500</h1><p>Внутренняя ошибка сервера. Проверьте логи.</p>
        <a href="/">← На главную</a></body></html>
        """,
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Default data seeder
# ---------------------------------------------------------------------------

def _seed_default_templates() -> None:
    """
    Populate the database with sensible default backup templates
    for the most common network device types.
    Only runs if the templates table is empty.
    """
    from app.database import SessionLocal
    from app.models import BackupTemplate

    db = SessionLocal()
    try:
        if db.query(BackupTemplate).count() > 0:
            return  # Already seeded

        defaults = [
            BackupTemplate(
                name="Cisco IOS / IOS-XE",
                description="Full running-config backup for Cisco IOS and IOS-XE",
                device_type="cisco_ios",
                commands="terminal length 0\nshow running-config\nshow version",
            ),
            BackupTemplate(
                name="Cisco IOS-XR",
                description="Running config for Cisco IOS-XR",
                device_type="cisco_xr",
                commands="terminal length 0\nshow running-config\nshow version",
            ),
            BackupTemplate(
                name="Cisco NX-OS",
                description="Running config for Cisco NX-OS (Nexus)",
                device_type="cisco_nxos",
                commands="terminal length 0\nshow running-config\nshow version",
            ),
            BackupTemplate(
                name="Cisco ASA",
                description="Running config for Cisco ASA firewall",
                device_type="cisco_asa",
                commands="terminal pager 0\nshow running-config\nshow version",
            ),
            BackupTemplate(
                name="Juniper JunOS",
                description="Full config for Juniper JunOS devices",
                device_type="juniper_junos",
                commands="set cli screen-length 0\nshow configuration | no-more\nshow version",
            ),
            BackupTemplate(
                name="Arista EOS",
                description="Running config for Arista EOS",
                device_type="arista_eos",
                commands="terminal length 0\nshow running-config\nshow version",
            ),
            BackupTemplate(
                name="Huawei VRP",
                description="Current config for Huawei VRP devices",
                device_type="huawei",
                commands="screen-length 0 temporary\ndisplay current-configuration\ndisplay version",
            ),
            BackupTemplate(
                name="MikroTik RouterOS",
                description="Full config export for MikroTik",
                device_type="mikrotik_routeros",
                commands="/export\n/system resource print",
            ),
            BackupTemplate(
                name="HP Comware",
                description="Running config for HP/H3C Comware",
                device_type="hp_comware",
                commands="screen-length disable\ndisplay current-configuration\ndisplay version",
            ),
        ]

        for tmpl in defaults:
            db.add(tmpl)
        db.commit()
        logger.info("Seeded %d default backup templates", len(defaults))

    except Exception as exc:
        logger.error("Template seeding failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        workers=1,  # SQLite + single process is safest
        log_level="debug" if settings.app.debug else "info",
        access_log=settings.app.debug,
    )
