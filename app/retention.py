"""
retention.py — Backup retention policy engine.

Deletes BackupJob records older than the configured retention period.
Runs after every successful backup sweep and as a standalone daily job.

Retention priority:
  device.retention_days  (set per-device in the UI)
      └─ None → global app_settings["retention_days"]
                    └─ missing → DEFAULT_RETENTION_DAYS (365)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.database import SessionLocal
from app.models import AppSetting, BackupJob, Device

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 365


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_global_retention_days(db) -> int:
    """Read global retention setting from app_settings table."""
    row = db.query(AppSetting).filter(AppSetting.key == "retention_days").first()
    if row and row.value:
        try:
            val = int(row.value)
            return val if val > 0 else DEFAULT_RETENTION_DAYS
        except ValueError:
            pass
    return DEFAULT_RETENTION_DAYS


def get_effective_retention(device: Device, global_days: int) -> int:
    """Return the effective retention for a device (per-device or global)."""
    if device.retention_days is not None and device.retention_days > 0:
        return device.retention_days
    return global_days


# ---------------------------------------------------------------------------
# Core pruning
# ---------------------------------------------------------------------------

def prune_device_jobs(db, device_id: int, retention_days: int) -> int:
    """
    Delete BackupJob rows for device_id that are older than retention_days.
    Returns the number of rows deleted.
    Does NOT commit — caller must commit.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = (
        db.query(BackupJob)
        .filter(
            BackupJob.device_id == device_id,
            BackupJob.started_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
    return deleted


def _run_git_gc() -> None:
    """Run git gc --auto to repack loose objects after pruning."""
    try:
        from app.git_manager import get_git_manager
        git_mgr = get_git_manager()
        if git_mgr._repo:
            git_mgr._repo.git.gc("--auto", "--quiet")
            logger.debug("git gc --auto completed")
    except Exception as exc:
        logger.debug("git gc skipped (non-critical): %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_retention_for_all_devices() -> None:
    """
    Apply the retention policy to all devices.
    Called daily by the scheduler and optionally after each backup sweep.
    """
    db = SessionLocal()
    try:
        global_days = get_global_retention_days(db)
        devices = db.query(Device).all()

        total_deleted = 0
        for device in devices:
            days = get_effective_retention(device, global_days)
            deleted = prune_device_jobs(db, device.id, days)
            if deleted:
                logger.info(
                    "Retention: pruned %d old job(s) for '%s' (policy: %d days)",
                    deleted, device.name, days,
                )
                total_deleted += deleted

        if total_deleted:
            db.commit()
            logger.info("Retention sweep complete — %d record(s) deleted", total_deleted)
            _run_git_gc()
        else:
            logger.debug("Retention sweep: nothing to prune")

    except Exception as exc:
        logger.error("Retention sweep failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def run_retention_for_device(device_id: int) -> int:
    """
    Apply retention policy to a single device.
    Returns the number of records pruned.
    """
    db = SessionLocal()
    try:
        device = db.get(Device, device_id)
        if not device:
            return 0
        global_days = get_global_retention_days(db)
        days = get_effective_retention(device, global_days)
        deleted = prune_device_jobs(db, device_id, days)
        if deleted:
            db.commit()
            logger.info(
                "Retention: pruned %d old job(s) for '%s' (policy: %d days)",
                deleted, device.name, days,
            )
        return deleted
    except Exception as exc:
        logger.error("Retention for device %d failed: %s", device_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()
