"""
notifications.py — Webhook dispatcher for failure alerts.

Supports Rocket.Chat / Mattermost / Slack-compatible webhooks.
Optionally includes git diff in backup failure payloads.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
WEBHOOK_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _backup_failure_payload(
    device_name: str,
    hostname: str,
    error: str,
    diff_text: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = (
        f":x: **Backup FAILED** — `{device_name}` (`{hostname}`)\n"
        f"**Time:** {now}\n"
        f"**Error:** {error}"
    )
    attachment = {
        "color": "#FF0000",
        "title": f"Backup failure: {device_name}",
        "text": error,
        "fields": [
            {"title": "Device", "value": device_name, "short": True},
            {"title": "Host",   "value": hostname,    "short": True},
            {"title": "Time",   "value": now,         "short": True},
        ],
    }

    # Append git diff if provided and not too large
    if diff_text:
        max_diff_chars = 3000
        truncated = diff_text[:max_diff_chars]
        if len(diff_text) > max_diff_chars:
            truncated += f"\n… (truncated, {len(diff_text)} chars total)"
        attachment["fields"].append({
            "title": "Config Diff",
            "value": f"```diff\n{truncated}\n```",
            "short": False,
        })

    return {"text": text, "attachments": [attachment]}


def _ping_failure_payload(device_name: str, hostname: str) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "text": (
            f":warning: **Device UNREACHABLE** — `{device_name}` (`{hostname}`)\n"
            f"**Time:** {now}"
        ),
        "attachments": [{
            "color": "#FF8C00",
            "title": f"Ping failure: {device_name}",
            "fields": [
                {"title": "Device", "value": device_name, "short": True},
                {"title": "Host",   "value": hostname,    "short": True},
                {"title": "Time",   "value": now,         "short": True},
            ],
        }],
    }


# ---------------------------------------------------------------------------
# HTTP sender
# ---------------------------------------------------------------------------

def _send_webhook(url: str, payload: dict) -> bool:
    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            if resp.is_success:
                return True
            logger.warning("Webhook non-2xx: %s -> %d", url, resp.status_code)
            return False
    except httpx.TimeoutException:
        logger.warning("Webhook timeout: %s", url)
        return False
    except Exception as exc:
        logger.error("Webhook error %s: %s", url, exc)
        return False


def _get_active_webhooks(require_backup: bool = False, require_ping: bool = False):
    """Yield (url, send_diff) tuples for enabled matching webhooks."""
    try:
        from app.database import SessionLocal
        from app.models import NotificationWebhook
        db = SessionLocal()
        try:
            for wh in db.query(NotificationWebhook).filter(NotificationWebhook.enabled == True).all():
                if require_backup and not wh.on_backup_fail:
                    continue
                if require_ping and not wh.on_ping_fail:
                    continue
                yield wh.url, getattr(wh, "send_diff", False)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not query DB webhooks: %s", exc)

    # Config-file fallback (no diff support)
    if settings.notifications.enabled:
        for url in settings.notifications.webhooks:
            yield url, False


# ---------------------------------------------------------------------------
# Public dispatch functions
# ---------------------------------------------------------------------------

def dispatch_backup_failure(
    device_name: str,
    hostname: str,
    error: str,
    diff_text: Optional[str] = None,
) -> None:
    if not settings.notifications.on_backup_fail:
        return
    for url, send_diff in _get_active_webhooks(require_backup=True):
        diff = diff_text if send_diff else None
        payload = _backup_failure_payload(device_name, hostname, error, diff)
        _send_webhook(url, payload)


def dispatch_ping_failure(device_name: str, hostname: str) -> None:
    if not settings.notifications.on_ping_fail:
        return
    payload = _ping_failure_payload(device_name, hostname)
    for url, _ in _get_active_webhooks(require_ping=True):
        _send_webhook(url, payload)
