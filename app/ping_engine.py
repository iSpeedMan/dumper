"""
ping_engine.py — Concurrent ICMP ping engine.
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

FAIL_THRESHOLD = 2


def _ping_host(hostname: str, timeout: float = 2.0) -> Tuple[bool, Optional[float]]:
    """Ping a single host.  Returns (reachable, rtt_ms).

    Probe order (stops at first definitive answer):
      1. icmplib privileged=True  — raw ICMP socket; needs CAP_NET_RAW / root.
      2. icmplib privileged=False — DGRAM socket; needs net.ipv4.ping_group_range.
         NOTE: if this returns is_alive=False we do NOT trust it — the kernel may
         simply have denied the socket without raising an exception. Fall through.
      3. subprocess ping           — uses the setuid system binary; always works.
    """
    # 1. Try raw ICMP (works when service has CAP_NET_RAW or runs as root)
    try:
        from icmplib import ping as icmp_ping
        result = icmp_ping(hostname, count=1, timeout=timeout, privileged=True)
        return result.is_alive, (result.avg_rtt if result.is_alive else None)
    except Exception:
        pass  # PermissionError or not installed — try next

    # 2. Try unprivileged icmplib DGRAM socket
    try:
        from icmplib import ping as icmp_ping
        result = icmp_ping(hostname, count=1, timeout=timeout, privileged=False)
        if result.is_alive:
            # Positive result is reliable; negative may be a false-negative
            # (kernel denied socket silently) — fall through to subprocess.
            return True, result.avg_rtt
    except Exception:
        pass  # PermissionError — fall through

    # 3. subprocess ping — most portable; uses setuid binary on Linux/macOS
    try:
        system = platform.system().lower()
        if system == "windows":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), hostname]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), hostname]

        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout + 1,
        )
        return proc.returncode == 0, None
    except Exception as exc:
        logger.debug("subprocess ping failed for %s: %s", hostname, exc)
        return False, None


def _check_device(device_id: int) -> Tuple[int, bool, Optional[float]]:
    """Check a single device and update its DB status."""
    db: Session = SessionLocal()
    try:
        device: Optional[Device] = db.get(Device, device_id)
        if not device:
            return device_id, False, None

        is_reachable, rtt_ms = _ping_host(device.hostname)
        now = datetime.now(timezone.utc)

        ping_status = (
            db.query(PingStatus)
            .filter(PingStatus.device_id == device_id)
            .first()
        )
        if ping_status is None:
            ping_status = PingStatus(
                device_id=device_id,
                consecutive_failures=0,
            )
            db.add(ping_status)

        ping_status.is_reachable = is_reachable
        ping_status.rtt_ms = int(rtt_ms) if rtt_ms else None
        ping_status.last_checked = now

        if is_reachable:
            ping_status.consecutive_failures = 0
            device.status = DeviceStatus.ONLINE
            device.last_seen = now
        else:
            # Guard against None (defensive, shouldn't happen with nullable=False + default)
            current_failures = ping_status.consecutive_failures or 0
            ping_status.consecutive_failures = current_failures + 1
            if ping_status.consecutive_failures >= FAIL_THRESHOLD:
                device.status = DeviceStatus.OFFLINE

        db.commit()

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


def run_ping_for_all_devices() -> Dict[int, bool]:
    """Ping all devices in the database concurrently."""
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
