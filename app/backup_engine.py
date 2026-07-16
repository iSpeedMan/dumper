"""
backup_engine.py — SSH/Telnet backup engine using Netmiko.

Responsibilities:
- Connect to a device via SSH or Telnet
- Execute a template's command chain
- Clean up terminal output (remove ANSI escapes, prompts, pagination artefacts)
- Save the result via GitManager
- Record the outcome in a BackupJob row
- Dispatch failure notifications
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
from sqlalchemy.orm import Session

from app.config import settings
from app.crypto import decrypt
from app.database import SessionLocal
from app.git_manager import get_git_manager
from app.models import BackupJob, BackupJobStatus, Device, DeviceStatus

logger = logging.getLogger(__name__)

# ANSI escape sequence regex — strips color codes and cursor movement
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
# Repeated spaces/tabs collapse
WHITESPACE_NORMALIZE = re.compile(r"[ \t]+")


# ---------------------------------------------------------------------------
# Output cleaning
# ---------------------------------------------------------------------------

def clean_output(raw: str) -> str:
    """
    Strip terminal artefacts from raw device output:
    - ANSI escape sequences
    - Terminal paging prompts (--More--, <--- More --->)
    - Backspace and carriage-return sequences
    - Blank lines at start/end (preserve internal blank lines)
    """
    # Remove ANSI escapes
    text = ANSI_ESCAPE.sub("", raw)
    # Remove backspace sequences
    text = re.sub(r".\x08", "", text)
    # Remove carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove common pagination prompts
    text = re.sub(r"--More--|<--- More --->|\[More\]", "", text, flags=re.IGNORECASE)
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.splitlines()]
    # Join and strip leading/trailing blank lines
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Single device backup
# ---------------------------------------------------------------------------

def _run_backup_for_device(device_id: int) -> Tuple[bool, str]:
    """
    Execute a backup for a single device. Runs in a thread pool worker.

    Returns:
        (success: bool, message: str)
    """
    db: Session = SessionLocal()
    start_time = time.monotonic()

    try:
        # Load device with related template and group
        device: Optional[Device] = db.get(Device, device_id)
        if not device:
            return False, f"Device ID {device_id} not found"

        if not device.backup_enabled:
            return False, "Backup disabled for this device"

        # Create a BackupJob record in RUNNING state
        job = BackupJob(
            device_id=device.id,
            status=BackupJobStatus.RUNNING,
            triggered_by="scheduler",
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info("Starting backup for device '%s' (%s)", device.name, device.hostname)

        # Decrypt credentials
        try:
            plain_password = decrypt(device.password)
            plain_username = decrypt(device.username)
            plain_enable = decrypt(device.enable_secret) if device.enable_secret else ""
        except ValueError as exc:
            return _fail_job(db, job, device, f"Credential decryption error: {exc}", start_time)

        # Build Netmiko connection params
        conn_params: Dict = {
            "device_type": device.netmiko_device_type,
            "host": device.hostname,
            "port": device.port,
            "username": plain_username,
            "password": plain_password,
            "timeout": 30,
            "auth_timeout": 20,
            "banner_timeout": 20,
            "fast_cli": False,
        }
        if plain_enable:
            conn_params["secret"] = plain_enable
        if device.connection_type.value == "telnet":
            conn_params["device_type"] = device.netmiko_device_type + "_telnet"

        # Get command list from template (or fall back to a minimal default)
        if device.template:
            commands = device.template.get_commands()
        else:
            commands = _default_commands(device.netmiko_device_type)

        # Connect and run commands
        try:
            output_parts: List[str] = []
            with ConnectHandler(**conn_params) as net_connect:
                # Enter enable mode if secret is configured
                if plain_enable:
                    net_connect.enable()

                for cmd in commands:
                    if cmd.lower() in ("enable",):
                        # Already handled above
                        continue
                    output = net_connect.send_command(
                        cmd,
                        read_timeout=60,
                        expect_string=None,
                    )
                    output_parts.append(f"! === {cmd} ===\n{output}")

            raw_output = "\n\n".join(output_parts)
            clean = clean_output(raw_output)

        except NetmikoAuthenticationException as exc:
            return _fail_job(db, job, device, f"Authentication failed: {exc}", start_time)
        except NetmikoTimeoutException as exc:
            return _fail_job(db, job, device, f"Connection timed out: {exc}", start_time)
        except Exception as exc:
            return _fail_job(db, job, device, f"Connection error: {exc}", start_time)

        # Save to Git
        group_name = device.group.name if device.group else None
        git_mgr = get_git_manager()

        try:
            commit_hash, diff = git_mgr.save_and_commit(
                device_name=device.name,
                group_name=group_name,
                config_content=clean,
                device_hostname=device.hostname,
            )
        except Exception as exc:
            logger.error("Git commit failed for device '%s': %s", device.name, exc)
            commit_hash, diff = None, ""

        # Determine config file path
        from app.git_manager import _safe_filename
        safe_group = _safe_filename(group_name or "ungrouped")
        safe_dev = _safe_filename(device.name)
        config_file_path = f"{safe_group}/{safe_dev}/config.txt"

        duration = int(time.monotonic() - start_time)

        # Update job as SUCCESS
        job.status = BackupJobStatus.SUCCESS
        job.commit_hash = commit_hash
        job.config_file_path = config_file_path
        job.raw_output = clean
        job.duration_seconds = duration
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Backup SUCCESS for '%s' in %ds, commit=%s",
            device.name, duration, (commit_hash or "N/A")[:8],
        )
        return True, f"Success — commit {commit_hash[:8] if commit_hash else 'N/A'}"

    except Exception as exc:
        logger.exception("Unexpected error during backup of device ID %s: %s", device_id, exc)
        return False, str(exc)
    finally:
        db.close()


def _fail_job(
    db: Session,
    job: BackupJob,
    device: Device,
    error_msg: str,
    start_time: float,
) -> Tuple[bool, str]:
    """Mark a job as FAILED, persist, dispatch notification."""
    duration = int(time.monotonic() - start_time)
    job.status = BackupJobStatus.FAILED
    job.error_message = error_msg
    job.duration_seconds = duration
    job.finished_at = datetime.now(timezone.utc)

    # Update device status
    device.status = DeviceStatus.OFFLINE
    db.commit()

    logger.error("Backup FAILED for '%s': %s", device.name, error_msg)

    # Async-safe: dispatch notification in caller thread
    try:
        from app.notifications import dispatch_backup_failure
        dispatch_backup_failure(device.name, device.hostname, error_msg)
    except Exception as notify_exc:
        logger.warning("Failed to dispatch notification: %s", notify_exc)

    return False, error_msg


def _default_commands(device_type: str) -> List[str]:
    """Return a minimal fallback command set for common device types."""
    defaults = {
        "cisco_ios": ["terminal length 0", "show running-config"],
        "cisco_xr": ["terminal length 0", "show running-config"],
        "cisco_nxos": ["terminal length 0", "show running-config"],
        "cisco_asa": ["terminal pager 0", "show running-config"],
        "juniper": ["show configuration | no-more"],
        "juniper_junos": ["set cli screen-length 0", "show configuration | no-more"],
        "huawei": ["screen-length 0 temporary", "display current-configuration"],
        "mikrotik_routeros": ["/export"],
        "hp_comware": ["screen-length disable", "display current-configuration"],
        "arista_eos": ["terminal length 0", "show running-config"],
    }
    # Try exact match, then prefix match
    if device_type in defaults:
        return defaults[device_type]
    for key, cmds in defaults.items():
        if device_type.startswith(key.split("_")[0]):
            return cmds
    return ["show running-config"]


# ---------------------------------------------------------------------------
# Batch backup runner
# ---------------------------------------------------------------------------

def run_backup_for_devices(device_ids: List[int], triggered_by: str = "scheduler") -> Dict[int, Tuple[bool, str]]:
    """
    Run backups concurrently for a list of device IDs.
    Uses a ThreadPoolExecutor with max_workers from config.

    Returns a dict: {device_id: (success, message)}
    """
    max_workers = min(settings.scheduler.max_workers, len(device_ids))
    results: Dict[int, Tuple[bool, str]] = {}

    if not device_ids:
        return results

    logger.info("Starting batch backup for %d device(s) with %d workers", len(device_ids), max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_id: Dict[Future, int] = {
            executor.submit(_run_backup_for_device, dev_id): dev_id
            for dev_id in device_ids
        }
        for future in as_completed(future_to_id):
            dev_id = future_to_id[future]
            try:
                results[dev_id] = future.result()
            except Exception as exc:
                logger.error("Backup task raised exception for device %d: %s", dev_id, exc)
                results[dev_id] = (False, str(exc))

    ok = sum(1 for s, _ in results.values() if s)
    logger.info("Batch backup complete: %d/%d succeeded", ok, len(device_ids))
    return results


def run_backup_for_device(device_id: int, triggered_by: str = "manual") -> Tuple[bool, str]:
    """Convenience wrapper to back up a single device (e.g. from the UI)."""
    return _run_backup_for_device(device_id)
