# Dumper

**Network Configuration Backup Manager** — автоматически подключается к сетевому оборудованию (Cisco, Mikrotik, Juniper и др.) через SSH/Telnet, сохраняет конфигурации в локальный Git-репозиторий и предоставляет веб-интерфейс для просмотра истории, diff-сравнений и управления устройствами.

---

## Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Шаблоны | Jinja2 SSR (серверный рендеринг) |
| БД | SQLite (`data/dumper.db`) |
| Конфиги | Локальный Git-репозиторий (`configs_repo/`) |
| Планировщик | APScheduler — cron-бэкапы + ICMP ping-sweep |
| Подключение | Netmiko (SSH/Telnet) |

---

## Быстрый старт (разработка)

```bash
git clone <repo> /opt/dumper
cd /opt/dumper

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.yaml.sample config.yaml
# Отредактируйте config.yaml — укажите secret_key и master_key

python main.py
# → http://localhost:5000
```

При первом запуске перейдите на `/setup` и создайте учётную запись администратора.

---

## Установка как системный сервис (production)

### Требования

- Debian 12 / Ubuntu 22.04+ (systemd)
- Python 3.10+
- root-доступ

### Автоматическая установка

```bash
git clone <repo> /opt/dumper
cd /opt/dumper
cp config.yaml.sample config.yaml
# Отредактируйте config.yaml!

sudo bash install.sh
```

Скрипт выполнит:
1. Создание системного пользователя `dumper` (без shell, без домашней директории)
2. Создание Python venv и установку зависимостей
3. Создание директорий `data/` и `configs_repo/` с правильными правами
4. Настройку git-идентичности для пользователя `dumper`
5. Установку и запуск `dumper.service`

### Ручная установка

```bash
# 1. Системный пользователь
sudo useradd -r -s /sbin/nologin -d /opt/dumper dumper

# 2. venv и зависимости
python3 -m venv /opt/dumper/venv
/opt/dumper/venv/bin/pip install -r /opt/dumper/requirements.txt

# 3. Директории и права
sudo mkdir -p /opt/dumper/data /opt/dumper/configs_repo
sudo chown -R dumper:dumper /opt/dumper/data /opt/dumper/configs_repo
sudo chown root:dumper /opt/dumper/config.yaml
sudo chmod 640 /opt/dumper/config.yaml

# 4. Сервис
sudo cp /opt/dumper/dumper.service /etc/systemd/system/dumper.service
sudo systemctl daemon-reload
sudo systemctl enable --now dumper
```

### Если сервис уже не запускается (ошибка прав)

Симптом в `journalctl -u dumper`:
```
sqlite3.OperationalError: attempt to write a readonly database
```

Причина: директории `data/` и/или `configs_repo/` были созданы от `root` при ручном запуске.

Лечение:
```bash
sudo chown -R dumper:dumper /opt/dumper/data /opt/dumper/configs_repo
sudo systemctl restart dumper
```

После обновления `dumper.service` (добавлены `ExecStartPre=+/bin/chown ...`) эта проблема устраняется автоматически при каждом старте сервиса.

---

## Конфигурация

Основной файл: `/opt/dumper/config.yaml` (создаётся из `config.yaml.sample`).

### Ключевые параметры

```yaml
app:
  secret_key: "..."        # Ключ подписи сессий — сгенерируйте: openssl rand -hex 32
  debug: false
  host: "0.0.0.0"
  port: 5000

database:
  path: "data/dumper.db"

encryption:
  master_key: "..."        # AES-256-GCM ключ шифрования паролей устройств
                           # Сгенерируйте: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
                           # ОБЯЗАТЕЛЬНО сохраните резервную копию!
```

### Переменные окружения (override config.yaml)

| Переменная | Параметр |
|-----------|---------|
| `DUMPER_CONFIG` | Путь к config.yaml (по умолчанию `config.yaml`) |
| `DUMPER_SECRET_KEY` | `app.secret_key` |
| `DUMPER_MASTER_KEY` | `encryption.master_key` |

Для хранения секретов вне unit-файла используйте `EnvironmentFile`:
```ini
# /etc/dumper/secrets.env
DUMPER_SECRET_KEY=...
DUMPER_MASTER_KEY=...
```
```ini
# dumper.service [Service]
EnvironmentFile=/etc/dumper/secrets.env
```

---

## Управление сервисом

```bash
# Статус
sudo systemctl status dumper

# Логи (realtime)
sudo journalctl -u dumper -f

# Перезапуск (например, после изменения config.yaml)
sudo systemctl restart dumper

# Остановка
sudo systemctl stop dumper

# Отключить автозапуск
sudo systemctl disable dumper
```

---

## ICMP Ping Sweep и CAP_NET_RAW

Если включён ping-sweep и сервис запускается не от root, он не сможет отправлять raw ICMP-пакеты. Для выдачи нужной capability без запуска от root раскомментируйте в `dumper.service`:

```ini
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
```

Либо используйте утилиту `ping` через subprocess (зависит от реализации в `app/scheduler.py`).

---

## Структура проекта

```
/opt/dumper/
├── main.py                  # Точка входа (FastAPI app + lifespan)
├── config.yaml              # Конфигурация (gitignored)
├── config.yaml.sample       # Шаблон конфигурации
├── dumper.service           # systemd unit
├── install.sh               # Скрипт установки
├── requirements.txt
├── app/
│   ├── config.py            # Pydantic-модель config.yaml
│   ├── database.py          # SQLAlchemy engine, init_db()
│   ├── models.py            # ORM-модели
│   ├── security.py          # Аутентификация, middleware
│   ├── scheduler.py         # APScheduler jobs
│   ├── i18n.py              # Переводы (ru/en)
│   ├── git_manager.py       # Git-операции с configs_repo/
│   └── routes/              # FastAPI роутеры
│       ├── auth.py
│       ├── dashboard.py
│       ├── devices.py
│       ├── diff_viewer.py
│       ├── groups.py
│       ├── settings.py
│       ├── templates.py
│       └── users.py
├── templates/               # Jinja2 HTML-шаблоны
├── static/
│   ├── css/style.css        # Glassmorphism design system
│   └── js/
├── data/                    # SQLite БД (gitignored, создаётся автоматически)
└── configs_repo/            # Git-репозиторий конфигураций (gitignored)
```

---

## Обновление

```bash
cd /opt/dumper
sudo -u dumper git pull          # или скачайте архив и распакуйте

# Обновление зависимостей
sudo -u dumper /opt/dumper/venv/bin/pip install -r requirements.txt

# Обновление service-файла (если изменился)
sudo cp dumper.service /etc/systemd/system/dumper.service
sudo systemctl daemon-reload

sudo systemctl restart dumper
```

---

## Лицензия

MIT
