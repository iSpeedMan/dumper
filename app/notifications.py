"""
notifications.py — Webhook dispatcher for failure alerts.

Sends JSON POST requests compatible with:
  - Rocket.Chat Incoming Webhooks
  - Mattermost Incoming Webhooks
  - Slack-compatible webhooks

Notification triggers:
  - Backup failure
  - ICMP ping failure (device unreachable for FAIL_THRESHOLD consecutive checks)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Timeout for webhook HTTP requests
WEBHOOK_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _backup_failure_payload(device_name: str, hostname: str, error: str) -> dict:
    """Build a Rocket.Chat/Mattermost-compatible payload for backup failures."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "text": (
            f":x: **Backup FAILED** — `{device_name}` (`{hostname}`)\n"
            f"**Time:** {now}\n"
            f"**Error:** {error}"
        ),
        "attachments": [
            {
                "color": "#FF0000",
                "title": f"Backup failure: {device_name}",
                "text": error,
                "fields": [
                    {"title": "Device", "value": device_name, "short": True},
                    {"title": "Host", "value": hostname, "short": True},
                    {"title": "Time", "value": now, "short": True},
                ],
            }
        ],
    }


def _ping_failure_payload(device_name: str, hostname: str) -> dict:
    """Build payload for device unreachable alerts."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "text": (
            f":warning: **Device UNREACHABLE** — `{device_name}` (`{hostname}`)\n"
            f"**Time:** {now}"
        ),
        "attachments": [
            {
                "color": "#FF8C00",
                "title": f"Ping failure: {device_name}",
                "fields": [
                    {"title": "Device", "value": device_name, "short": True},
                    {"title": "Host", "value": hostname, "short": True},
                    {"title": "Time", "value": now, "short": True},
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# HTTP sender
# ---------------------------------------------------------------------------

def _send_webhook(url: str, payload: dict) -> bool:
    """
    POST payload to a single webhook URL.
    Returns True on HTTP 2xx, False otherwise.
    """
    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            if resp.is_success:
                logger.debug("Webhook OK: %s -> %d", url, resp.status_code)
                return True
            else:
                logger.warning("Webhook non-2xx: %s -> %d %s", url, resp.status_code, resp.text[:200])
                return False
    except httpx.TimeoutException:
        logger.warning("Webhook timeout: %s", url)
        return False
    except Exception as exc:
        logger.error("Webhook error %s: %s", url, exc)
        return False


def _get_active_webhooks(require_backup: bool = False, require_ping: bool = False):
    """Yield enabled webhook URLs from the database (plus config file fallback)."""
    # Database webhooks
    try:
        from app.database import SessionLocal
        from app.models import NotificationWebhook
        db = SessionLocal()
        try:
            query = db.query(NotificationWebhook).filter(NotificationWebhook.enabled == True)
            for wh in query.all():
                if require_backup and not wh.on_backup_fail:
                    continue
                if require_ping and not wh.on_ping_fail:
                    continue
                yield wh.url
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not query DB webhooks: %s", exc)

    # Fallback: config file webhooks
    if settings.notifications.enabled:
        for url in settings.notifications.webhooks:
            yield url


# ---------------------------------------------------------------------------
# Public dispatch functions
# ---------------------------------------------------------------------------

def dispatch_backup_failure(device_name: str, hostname: str, error: str) -> None:
    """Send backup failure notification to all configured webhooks."""
    if not settings.notifications.on_backup_fail:
        return
    payload = _backup_failure_payload(device_name, hostname, error)
    for url in _get_active_webhooks(require_backup=True):
        _send_webhook(url, payload)


def dispatch_ping_failure(device_name: str, hostname: str) -> None:
    """Send ping failure notification to all configured webhooks."""
    if not settings.notifications.on_ping_fail:
        return
    payload = _ping_failure_payload(device_name, hostname)
    for url in _get_active_webhooks(require_ping=True):
        _send_webhook(url, payload)
