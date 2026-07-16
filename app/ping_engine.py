"""
ping_engine.py — Concurrent ICMP ping engine.

Uses icmplib for pure-Python ICMP pings (requires raw socket / root OR
falls back to system 'ping' binary if raw sockets are unavailable).
Runs in a ThreadPoolExecutor to handle 1000+ devices concurrently.
Updates device status and PingStatus rows in the database.
Dispatches notifications on ping failure.
"""

import logging
import platform
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Device, DeviceStatus, PingStatus

logger = logging.getLogger(__name__)

# Number of consecutive failures before we consider a device truly down
FAIL_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Low-level ping
# ---------------------------------------------------------------------------

def _ping_host(hostname: str, timeout: float = 2.0) -> Tuple[bool, Optional[float]]:
    """
    Ping a single host. Returns (reachable, rtt_ms).
    Tries icmplib first; falls back to system ping command.
    """
    # --- Try icmplib (requires CAP_NET_RAW or root) ---
    try:
        from icmplib import ping as icmp_ping, SocketPermissionError
        result = icmp_ping(hostname, count=1, timeout=timeout, privileged=False)
        return result.is_alive, (result.avg_rtt if result.is_alive else None)
    except Exception:
        pass

    # --- Fallback: system ping command ---
    try:
        system = platform.system().lower()
        if system == "windows":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), hostname]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), hostname]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 1,
        )
        return proc.returncode == 0, None
    except Exception:
        return False, None


# ---------------------------------------------------------------------------
# Per-device ping worker
# ---------------------------------------------------------------------------

def _check_device(device_id: int) -> Tuple[int, bool, Optional[float]]:
    """
    Check a single device and update its DB status.
    Returns (device_id, is_reachable, rtt_ms).
    """
    db: Session = SessionLocal()
    try:
        device: Optional[Device] = db.get(Device, device_id)
        if not device:
            return device_id, False, None

        is_reachable, rtt_ms = _ping_host(device.hostname)
        now = datetime.now(timezone.utc)

        # Upsert PingStatus
        ping_status = (
            db.query(PingStatus)
            .filter(PingStatus.device_id == device_id)
            .first()
        )
        if ping_status is None:
            ping_status = PingStatus(device_id=device_id)
            db.add(ping_status)

        ping_status.is_reachable = is_reachable
        ping_status.rtt_ms = int(rtt_ms) if rtt_ms else None
        ping_status.last_checked = now

        if is_reachable:
            ping_status.consecutive_failures = 0
            device.status = DeviceStatus.ONLINE
            device.last_seen = now
        else:
            ping_status.consecutive_failures += 1
            if ping_status.consecutive_failures >= FAIL_THRESHOLD:
                device.status = DeviceStatus.OFFLINE

        db.commit()

        # Dispatch notification if just went offline
        if not is_reachable and ping_status.consecutive_failures == FAIL_THRESHOLD:
            try:
                from app.notifications import dispatch_ping_failure
                dispatch_ping_failure(device.name, device.hostname)
            except Exception as notify_exc:
                logger.warning("Ping failure notification error: %s", notify_exc)

        return device_id, is_reachable, rtt_ms

    except Exception as exc:
        logger.error("ping check error for device %d: %s", device_id, exc)
        return device_id, False, None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Batch ping runner
# ---------------------------------------------------------------------------

def run_ping_for_all_devices() -> Dict[int, bool]:
    """
    Ping all devices in the database concurrently.
    Returns dict {device_id: is_reachable}.
    """
    db: Session = SessionLocal()
    try:
        device_ids = [row[0] for row in db.query(Device.id).all()]
    finally:
        db.close()

    if not device_ids:
        return {}

    max_workers = min(settings.scheduler.ping_workers, len(device_ids))
    results: Dict[int, bool] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_check_device, did): did for did in device_ids}
        for future in as_completed(futures):
            dev_id, reachable, _ = future.result()
            results[dev_id] = reachable

    online = sum(1 for v in results.values() if v)
    logger.debug("Ping sweep: %d/%d online", online, len(results))
    return results
