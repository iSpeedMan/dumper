"""
models.py — SQLAlchemy ORM models for all database tables.
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

class User(Base):
    """Local user account for web UI authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=True)   # None for LDAP-only users
    is_admin = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_ldap = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_login = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class AppSetting(Base):
    """Key-value store for app settings editable from the UI (e.g. LDAP config)."""
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AppSetting {self.key!r}={self.value!r}>"


class DeviceGroup(Base):
    """Logical group for organizing devices."""
    __tablename__ = "device_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    devices = relationship("Device", back_populates="group", lazy="select")

    def __repr__(self) -> str:
        return f"<DeviceGroup id={self.id} name={self.name!r}>"


class Device(Base):
    """A managed network device. Credentials stored AES-256-GCM encrypted."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    hostname = Column(String(256), nullable=False)
    port = Column(Integer, default=22, nullable=False)
    connection_type = Column(Enum(ConnectionType), default=ConnectionType.SSH, nullable=False)
    netmiko_device_type = Column(String(64), default="cisco_ios", nullable=False)

    # Encrypted credentials (AES-256-GCM via crypto.py)
    username = Column(String(256), nullable=False)
    password = Column(String(512), nullable=False)
    enable_secret = Column(String(512), nullable=True)

    group_id = Column(Integer, ForeignKey("device_groups.id"), nullable=True)
    template_id = Column(Integer, ForeignKey("backup_templates.id"), nullable=True)
    custom_cron = Column(String(64), nullable=True)
    backup_enabled = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)

    status = Column(Enum(DeviceStatus), default=DeviceStatus.UNKNOWN, nullable=False)
    last_seen = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    group = relationship("DeviceGroup", back_populates="devices")
    template = relationship("BackupTemplate", back_populates="devices")
    backup_jobs = relationship("BackupJob", back_populates="device",
                               cascade="all, delete-orphan", lazy="dynamic")
    ping_status = relationship("PingStatus", back_populates="device",
                                uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Device id={self.id} name={self.name!r} host={self.hostname!r}>"


class BackupTemplate(Base):
    """Named sequence of CLI commands to collect device config."""
    __tablename__ = "backup_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    commands = Column(Text, nullable=False)
    device_type = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    devices = relationship("Device", back_populates="template")

    def get_commands(self) -> list[str]:
        return [
            line.strip()
            for line in (self.commands or "").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def __repr__(self) -> str:
        return f"<BackupTemplate id={self.id} name={self.name!r}>"


class BackupJob(Base):
    """Record of a single backup execution attempt."""
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    status = Column(Enum(BackupJobStatus), default=BackupJobStatus.PENDING, nullable=False)
    commit_hash = Column(String(64), nullable=True)
    config_file_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    raw_output = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    triggered_by = Column(String(64), default="scheduler", nullable=False)
    started_at = Column(DateTime, default=func.now(), nullable=False)
    finished_at = Column(DateTime, nullable=True)

    device = relationship("Device", back_populates="backup_jobs")

    def __repr__(self) -> str:
        return f"<BackupJob id={self.id} device_id={self.device_id} status={self.status}>"


class PingStatus(Base):
    """Latest ICMP ping result for a device (one row per device)."""
    __tablename__ = "ping_status"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), unique=True, nullable=False)

    is_reachable = Column(Boolean, default=False, nullable=False)
    rtt_ms = Column(Integer, nullable=True)
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
    send_diff = Column(Boolean, default=False, nullable=False)  # Include git diff in payload
    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<NotificationWebhook id={self.id} name={self.name!r}>"
