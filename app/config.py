"""
config.py — Loads and exposes application settings from config.yaml.
All other modules import from here; never read config files directly.
"""

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models for structured config validation
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    name: str = "Dumper"
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    secret_key: str = Field(default_factory=lambda: secrets.token_hex(32))
    timezone: str = "UTC"


class DatabaseConfig(BaseModel):
    path: str = "data/dumper.db"


class EncryptionConfig(BaseModel):
    master_key: str = ""


class GitConfig(BaseModel):
    repo_path: str = "configs_repo"
    author_name: str = "Dumper Bot"
    author_email: str = "dumper@localhost"


class SchedulerConfig(BaseModel):
    default_cron: str = "0 3 * * *"
    max_workers: int = 20
    ping_interval: int = 60
    ping_workers: int = 50


class NotificationsConfig(BaseModel):
    enabled: bool = False
    webhooks: List[str] = []
    on_backup_fail: bool = True
    on_ping_fail: bool = True


class LdapConfig(BaseModel):
    enabled: bool = False
    server: str = ""
    port: int = 389
    use_ssl: bool = False
    base_dn: str = ""
    user_search_filter: str = "(sAMAccountName={username})"
    bind_dn: str = ""
    bind_password: str = ""


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    encryption: EncryptionConfig = EncryptionConfig()
    git: GitConfig = GitConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    ldap: LdapConfig = LdapConfig()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(os.environ.get("DUMPER_CONFIG", "config.yaml"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load settings from YAML config file.
    Falls back to defaults if the file is missing.
    Values can be overridden by environment variables with DUMPER_ prefix.
    """
    raw: Dict[str, Any] = {}

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        print(f"[WARNING] Config file not found at '{CONFIG_PATH}'. Using defaults.")

    settings = Settings(**raw)

    # Allow env-var overrides for critical fields
    if env_key := os.environ.get("DUMPER_SECRET_KEY"):
        settings.app.secret_key = env_key
    if env_key := os.environ.get("DUMPER_MASTER_KEY"):
        settings.encryption.master_key = env_key

    # Ensure data directories exist
    Path(settings.database.path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.git.repo_path).mkdir(parents=True, exist_ok=True)

    return settings


# Convenience alias used throughout the app
settings = get_settings()
