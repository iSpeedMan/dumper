"""
scheduler.py — APScheduler-based background job scheduler.

Jobs:
  1. Ping sweep       — runs every N seconds (config: scheduler.ping_interval)
  2. Backup scheduler — runs cron jobs per-device (or global default cron)

The scheduler starts with the FastAPI app lifespan and stops cleanly on shutdown.
"""

import logging
from typing import Optional

import pytz
from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPool
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scheduler instance
# ---------------------------------------------------------------------------

_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """Return the global BackgroundScheduler (created lazily).

    Uses MemoryJobStore to avoid APScheduler's SQLAlchemy jobstore pickling
    limitations with ZoneInfo timezone objects (Python 3.9+). Jobs are
    re-registered from the DB on every startup, so persistence is not needed.
    pytz is used for timezone objects because APScheduler 3.x serializes them
    and ZoneInfo is not picklable in that context.
    """
    global _scheduler
    if _scheduler is None:
        # Resolve timezone — prefer pytz so APScheduler can handle it correctly
        try:
            tz = pytz.timezone(settings.app.timezone)
        except Exception:
            tz = pytz.utc

        jobstores = {
            "default": MemoryJobStore(),
        }
        executors = {
            "default": APSThreadPool(max_workers=settings.scheduler.max_workers),
        }
        job_defaults = {
            "coalesce": True,          # Merge missed runs into one
            "max_instances": 1,        # Don't allow parallel runs of same job
            "misfire_grace_time": 300, # Fire up to 5min late before skipping
        }
        _scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=tz,
        )
    return _scheduler


# ---------------------------------------------------------------------------
# Job functions (these run in background threads)
# ---------------------------------------------------------------------------

def _job_retention_sweep() -> None:
    """Background job: apply backup retention policy to all devices."""
    try:
        from app.retention import run_retention_for_all_devices
        run_retention_for_all_devices()
    except Exception as exc:
        logger.error("Retention sweep job failed: %s", exc)


def _job_ping_sweep() -> None:
    """Background job: ping all devices."""
    try:
        from app.ping_engine import run_ping_for_all_devices
        run_ping_for_all_devices()
    except Exception as exc:
        logger.error("Ping sweep job failed: %s", exc)


def _job_scheduled_backups() -> None:
    """
    Background job: run backups for all devices whose cron matches now,
    OR all devices using the default global schedule (this job runs on the
    default cron, individual devices with custom crons have their own jobs).
    """
    try:
        from app.database import SessionLocal
        from app.models import Device
        from app.backup_engine import run_backup_for_devices

        db = SessionLocal()
        try:
            # Select devices using the default schedule (no custom_cron)
            devices = (
                db.query(Device)
                .filter(Device.backup_enabled == True, Device.custom_cron.is_(None))
                .all()
            )
            device_ids = [d.id for d in devices]
        finally:
            db.close()

        if device_ids:
            logger.info("Scheduled backup starting for %d device(s)", len(device_ids))
            run_backup_for_devices(device_ids, triggered_by="scheduler")
        else:
            logger.debug("Scheduled backup: no devices to back up")

    except Exception as exc:
        logger.error("Scheduled backup job failed: %s", exc)


def _job_custom_backup(device_id: int) -> None:
    """Background job: run a backup for a single device (custom cron)."""
    try:
        from app.backup_engine import run_backup_for_device
        run_backup_for_device(device_id, triggered_by="scheduler")
    except Exception as exc:
        logger.error("Custom backup job failed for device %d: %s", device_id, exc)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _get_default_cron_from_db() -> str:
    """Read backup_cron from the app_settings table; fall back to config.yaml value."""
    try:
        from app.database import SessionLocal
        from app.models import AppSetting

        db = SessionLocal()
        try:
            row = db.query(AppSetting).filter(AppSetting.key == "backup_cron").first()
            if row and row.value and row.value.strip():
                return row.value.strip()
        finally:
            db.close()
    except Exception:
        pass
    return settings.scheduler.default_cron


def reschedule_default_backup(cron_expr: str) -> None:
    """Replace the running backup_default job with a new cron expression.

    Called by the settings route after the user saves a new schedule.
    Validates the expression before applying it.
    """
    trigger = _parse_cron(cron_expr)  # raises ValueError on bad input
    scheduler = get_scheduler()
    scheduler.add_job(
        _job_scheduled_backups,
        trigger=trigger,
        id="backup_default",
        name="Default Backup Schedule",
        replace_existing=True,
    )
    logger.info("Rescheduled default backup job (cron='%s')", cron_expr)


def start_scheduler() -> None:
    """
    Start the scheduler and register all recurring jobs.
    Safe to call multiple times — won't register duplicates.
    """
    scheduler = get_scheduler()

    if scheduler.running:
        logger.debug("Scheduler already running")
        return

    # --- 1. Ping sweep ---
    if not scheduler.get_job("ping_sweep"):
        scheduler.add_job(
            _job_ping_sweep,
            trigger=IntervalTrigger(seconds=settings.scheduler.ping_interval),
            id="ping_sweep",
            name="ICMP Ping Sweep",
            replace_existing=True,
        )
        logger.info(
            "Registered ping sweep job (interval=%ds)", settings.scheduler.ping_interval
        )

    # --- 2. Default scheduled backup ---
    # Priority: app_settings DB → config.yaml → built-in default "0 3 * * *"
    if not scheduler.get_job("backup_default"):
        cron_expr = _get_default_cron_from_db()
        try:
            trigger = _parse_cron(cron_expr)
            scheduler.add_job(
                _job_scheduled_backups,
                trigger=trigger,
                id="backup_default",
                name="Default Backup Schedule",
                replace_existing=True,
            )
            logger.info("Registered default backup job (cron='%s')", cron_expr)
        except Exception as exc:
            logger.error("Failed to register default backup job (cron='%s'): %s", cron_expr, exc)

    # --- 3. Daily retention sweep (04:00) ---
    if not scheduler.get_job("retention_sweep"):
        try:
            tz = pytz.timezone(settings.app.timezone)
        except Exception:
            tz = pytz.utc
        scheduler.add_job(
            _job_retention_sweep,
            trigger=CronTrigger(hour=4, minute=0, timezone=tz),
            id="retention_sweep",
            name="Backup Retention Sweep",
            replace_existing=True,
        )
        logger.info("Registered retention sweep job (daily at 04:00)")

    # --- 4. Register custom cron jobs for devices ---
    refresh_custom_device_jobs()

    scheduler.start()
    logger.info("Scheduler started (%s)", settings.app.timezone)


def stop_scheduler() -> None:
    """Gracefully stop the scheduler (called on app shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")


def refresh_custom_device_jobs() -> None:
    """
    Sync custom-cron backup jobs from the DB.
    Call this after adding, updating, or deleting a device with a custom cron.
    """
    scheduler = get_scheduler()

    try:
        from app.database import SessionLocal
        from app.models import Device

        db = SessionLocal()
        try:
            devices_with_cron = (
                db.query(Device)
                .filter(
                    Device.backup_enabled == True,
                    Device.custom_cron.isnot(None),
                )
                .all()
            )
        finally:
            db.close()

        active_ids = set()
        for device in devices_with_cron:
            job_id = f"backup_device_{device.id}"
            active_ids.add(job_id)
            try:
                trigger = _parse_cron(device.custom_cron)
                scheduler.add_job(
                    _job_custom_backup,
                    trigger=trigger,
                    id=job_id,
                    name=f"Backup: {device.name}",
                    kwargs={"device_id": device.id},
                    replace_existing=True,
                )
                logger.debug(
                    "Registered custom cron job '%s' for device '%s'",
                    device.custom_cron, device.name,
                )
            except Exception as exc:
                logger.error(
                    "Failed to register cron job for device '%s' (cron='%s'): %s",
                    device.name, device.custom_cron, exc,
                )

        # Remove jobs for devices that no longer have a custom cron
        for job in scheduler.get_jobs():
            if job.id.startswith("backup_device_") and job.id not in active_ids:
                scheduler.remove_job(job.id)
                logger.debug("Removed stale job %s", job.id)

    except Exception as exc:
        logger.error("refresh_custom_device_jobs failed: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_cron(cron_expr: str) -> CronTrigger:
    """
    Parse a standard 5-field cron expression into an APScheduler CronTrigger.
    Uses pytz timezone objects so APScheduler can serialize triggers correctly.
    Raises ValueError on invalid expressions.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Invalid cron expression '{cron_expr}': expected 5 fields "
            f"(minute hour day month weekday), got {len(parts)}"
        )
    minute, hour, day, month, day_of_week = parts
    try:
        tz = pytz.timezone(settings.app.timezone)
    except Exception:
        tz = pytz.utc
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=tz,
    )
