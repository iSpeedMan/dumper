# Dumper

Network configuration backup manager — Python/FastAPI monolithic application.

## Stack

- **Language**: Python 3.10+
- **Framework**: FastAPI + Jinja2 (SSR, no separate frontend)
- **Database**: SQLite via SQLAlchemy ORM
- **Backup engine**: Netmiko (SSH/Telnet)
- **Scheduler**: APScheduler (cron + interval jobs)
- **Git versioning**: GitPython
- **Encryption**: AES-256-GCM (cryptography library)

## Running on Replit

```bash
pip install -r requirements.txt
python main.py
```

App runs on **port 5000**.

Before first run, edit `config.yaml`:
1. Set `encryption.master_key` (generate with: `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`)
2. Set `app.secret_key` to any long random string

## User preferences

- Communicate in Russian
- Production-grade, clean, well-commented code
- Monolithic architecture: FastAPI + Jinja2 SSR
- No separate frontend build steps
