# 📦 Dumper

**Production-ready network configuration backup manager.**

Automatically connects to your network devices (routers, switches, firewalls) via SSH or Telnet, fetches running configurations, stores them in a Git repository with full version history, and shows diffs between any two backups through a clean web UI.

---

## Features

| Feature | Details |
|---|---|
| **Web UI** | FastAPI + Jinja2 SSR — no separate frontend build |
| **Device inventory** | Full CRUD with groups, templates, per-device settings |
| **Encrypted credentials** | AES-256-GCM (master key in `config.yaml`) |
| **Git versioning** | Every backup → Git commit. Diff viewer built-in |
| **Scheduler** | APScheduler cron — global default or per-device |
| **Concurrent backups** | ThreadPoolExecutor, configurable worker count |
| **ICMP ping** | Background ping sweep, live status on dashboard |
| **Notifications** | Rocket.Chat / Mattermost / Slack webhook support |
| **systemd service** | `dumper.service` included |

## Supported Device Types (via Netmiko)

`cisco_ios`, `cisco_xr`, `cisco_nxos`, `cisco_asa`, `juniper_junos`,
`arista_eos`, `huawei`, `hp_comware`, `mikrotik_routeros`, and all other
[Netmiko-supported platforms](https://github.com/ktbyers/netmiko#supported-platforms).

---

## Quick Start (Replit / Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate a master encryption key
python -c "
import base64, os
key = base64.urlsafe_b64encode(os.urandom(32)).decode()
print('Master key:', key)
"

# 3. Edit config.yaml
#    Set: encryption.master_key  (from step 2)
#    Set: app.secret_key         (any long random string)

# 4. Run
python main.py
# → Open http://localhost:5000
```

---

## Production Deployment (Linux / systemd)

```bash
# Create a dedicated user
sudo useradd -r -s /bin/false -d /opt/dumper dumper

# Deploy application files
sudo mkdir -p /opt/dumper
sudo cp -r . /opt/dumper/
sudo chown -R dumper:dumper /opt/dumper

# Create Python virtual environment
sudo -u dumper python3 -m venv /opt/dumper/venv
sudo -u dumper /opt/dumper/venv/bin/pip install -r /opt/dumper/requirements.txt

# Configure (edit master_key and secret_key)
sudo vim /opt/dumper/config.yaml

# Install and start service
sudo cp dumper.service /etc/systemd/system/dumper.service
sudo systemctl daemon-reload
sudo systemctl enable --now dumper

# Check status
sudo systemctl status dumper
sudo journalctl -u dumper -f
```

---

## Project Structure

```
dumper/
├── main.py                  # Entry point — FastAPI app factory
├── config.yaml              # Configuration (edit this!)
├── requirements.txt
├── dumper.service           # systemd service unit
│
├── app/
│   ├── config.py            # Settings loader (Pydantic)
│   ├── crypto.py            # AES-256-GCM encrypt/decrypt
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models.py            # ORM models (Device, BackupJob, etc.)
│   ├── backup_engine.py     # SSH/Telnet backup via Netmiko
│   ├── ping_engine.py       # Concurrent ICMP ping sweep
│   ├── git_manager.py       # Git versioning via GitPython
│   ├── scheduler.py         # APScheduler cron jobs
│   ├── notifications.py     # Webhook dispatcher
│   └── routes/
│       ├── dashboard.py     # / — live device status + recent jobs
│       ├── inventory.py     # /inventory/ — device CRUD
│       ├── templates_routes.py # /templates/ — command templates
│       ├── diff_viewer.py   # /diff/ — config diff viewer
│       └── settings.py      # /settings/ — webhooks + scheduler
│
├── templates/               # Jinja2 HTML templates
├── static/                  # CSS + JS
│   ├── css/style.css
│   └── js/main.js
│
├── data/                    # SQLite database (auto-created)
│   └── dumper.db
└── configs_repo/            # Git repository for device configs (auto-created)
```

---

## Configuration

Edit `config.yaml`:

```yaml
app:
  secret_key: "your-long-random-secret"
  port: 5000
  timezone: "Europe/Moscow"

encryption:
  master_key: "your-base64-32byte-key"   # CRITICAL — back this up!

scheduler:
  default_cron: "0 3 * * *"   # Daily at 03:00 AM
  max_workers: 20              # Max concurrent backup threads
  ping_interval: 60            # ICMP sweep every 60 seconds
```

---

## Security Notes

- **Master key**: If you lose `encryption.master_key`, all stored credentials become unreadable. Back it up securely (e.g., HashiCorp Vault, a secrets manager).
- **Rotate key**: Use `crypto.rotate_key()` to re-encrypt all credentials when rotating.
- **HTTPS**: In production, put Dumper behind an nginx/Caddy reverse proxy with TLS.
- **systemd hardening**: The included `dumper.service` uses `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`.

---

## License

MIT — feel free to use and adapt.
