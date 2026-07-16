"""
models.py — SQLAlchemy ORM models for all database tables.

Tables:
  - devices        : Network devices (routers, switches, firewalls)
  - device_groups  : Logical groupings of devices
  - backup_templates: Command templates per device type
  - backup_jobs    : Backup execution history
  - ping_status    : Latest ICMP ping result per device
  - notification_webhooks: Configured webhook endpoints
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DeviceStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


class BackupJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConnectionType(str, enum.Enum):
    SSH = "ssh"
    TELNET = "telnet"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DeviceGroup(Base):
    """Logical group for organizing devices (e.g. by site, role, vendor)."""
    __tablename__ = "device_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    devices = relationship("Device", back_populates="group", lazy="select")

    def __repr__(self) -> str:
        return f"<DeviceGroup id={self.id} name={self.name!r}>"


class Device(Base):
    """
    A managed network device. Credentials are stored AES-256-GCM encrypted.
    The 'netmiko_device_type' must match Netmiko's supported platform strings
    (e.g. 'cisco_ios', 'cisco_xr', 'juniper', 'huawei', 'mikrotik_routeros').
    """
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    hostname = Column(String(256), nullable=False)  # IP or FQDN
    port = Column(Integer, default=22, nullable=False)
    connection_type = Column(Enum(ConnectionType), default=ConnectionType.SSH, nullable=False)
    netmiko_device_type = Column(String(64), default="cisco_ios", nullable=False)

    # Encrypted credentials (AES-256-GCM via crypto.py)
    username = Column(String(256), nullable=False)        # encrypted
    password = Column(String(512), nullable=False)        # encrypted
    enable_secret = Column(String(512), nullable=True)    # encrypted, optional

    # Backup config
    group_id = Column(Integer, ForeignKey("device_groups.id"), nullable=True)
    template_id = Column(Integer, ForeignKey("backup_templates.id"), nullable=True)
    # Custom cron expression; None means use the global default
    custom_cron = Column(String(64), nullable=True)
    # Whether this device participates in scheduled backups
    backup_enabled = Column(Boolean, default=True, nullable=False)
    # Notes / description
    description = Column(Text, nullable=True)

    # Current status (updated by ping engine)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.UNKNOWN, nullable=False)
    last_seen = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    group = relationship("DeviceGroup", back_populates="devices")
    template = relationship("BackupTemplate", back_populates="devices")
    backup_jobs = relationship("BackupJob", back_populates="device",
                               cascade="all, delete-orphan", lazy="dynamic")
    ping_status = relationship("PingStatus", back_populates="device",
                                uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Device id={self.id} name={self.name!r} host={self.hostname!r}>"


class BackupTemplate(Base):
    """
    A named sequence of CLI commands to run on a device to collect its config.
    Commands are stored as a newline-separated list. Special directives:
      - 'enable'        : Send enable command (uses enable_secret)
      - 'terminal length 0' : Disable paging
      - Any other line  : Run as a CLI command, capture output
    """
    __tablename__ = "backup_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    # Newline-separated list of commands
    commands = Column(Text, nullable=False)
    # Expected device type this template targets (informational)
    device_type = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    devices = relationship("Device", back_populates="template")

    def get_commands(self) -> list[str]:
        """Return commands as a list, stripping blank lines and comments."""
        return [
            line.strip()
            for line in (self.commands or "").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def __repr__(self) -> str:
        return f"<BackupTemplate id={self.id} name={self.name!r}>"


class BackupJob(Base):
    """
    Record of a single backup execution attempt for a device.
    Stores outcome, error message, and the Git commit hash if successful.
    """
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    status = Column(Enum(BackupJobStatus), default=BackupJobStatus.PENDING, nullable=False)
    # Git commit SHA if backup was committed successfully
    commit_hash = Column(String(64), nullable=True)
    # Path to the saved config file relative to git repo root
    config_file_path = Column(String(512), nullable=True)
    # Error message if status == FAILED
    error_message = Column(Text, nullable=True)
    # Full output captured from device (may be large)
    raw_output = Column(Text, nullable=True)
    # Duration of the backup operation in seconds
    duration_seconds = Column(Integer, nullable=True)

    triggered_by = Column(String(64), default="scheduler", nullable=False)  # "scheduler" or "manual"
    started_at = Column(DateTime, default=func.now(), nullable=False)
    finished_at = Column(DateTime, nullable=True)

    device = relationship("Device", back_populates="backup_jobs")

    def __repr__(self) -> str:
        return f"<BackupJob id={self.id} device_id={self.device_id} status={self.status}>"


class PingStatus(Base):
    """Latest ICMP ping result for a device. One row per device (upserted)."""
    __tablename__ = "ping_status"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), unique=True, nullable=False)

    is_reachable = Column(Boolean, default=False, nullable=False)
    # Round-trip time in milliseconds
    rtt_ms = Column(Integer, nullable=True)
    # Number of consecutive failures (reset to 0 on success)
    consecutive_failures = Column(Integer, default=0, nullable=False)
    last_checked = Column(DateTime, default=func.now(), nullable=False)

    device = relationship("Device", back_populates="ping_status")

    def __repr__(self) -> str:
        return f"<PingStatus device_id={self.device_id} reachable={self.is_reachable}>"


class NotificationWebhook(Base):
    """A webhook endpoint to notify on backup/ping failures."""
    __tablename__ = "notification_webhooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    url = Column(String(1024), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    on_backup_fail = Column(Boolean, default=True, nullable=False)
    on_ping_fail = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<NotificationWebhook id={self.id} name={self.name!r}>"
