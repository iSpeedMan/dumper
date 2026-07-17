# 📦 Dumper

**Production-ready network configuration backup manager.**

Автоматически подключается к сетевым устройствам (роутеры, коммутаторы, межсетевые экраны) по SSH или Telnet, получает конфигурации, хранит их в Git-репозитории с полной историей версий и показывает диффы между любыми двумя бэкапами через чистый веб-интерфейс.

---

## Возможности

| Функция | Описание |
|---|---|
| **Web UI** | FastAPI + Jinja2 SSR — отдельная сборка фронтенда не нужна |
| **Метро-дизайн** | Metro UI: плоские квадратные углы, тёмная/светлая тема, адаптивный дизайн |
| **Инвентарь устройств** | Полный CRUD с группами, шаблонами команд, настройками на устройство |
| **Шифрование учётных данных** | AES-256-GCM (мастер-ключ в `config.yaml`) |
| **Git-версионирование** | Каждый бэкап → Git-коммит; встроенный просмотр диффов и снимков конфигурации |
| **Планировщик** | APScheduler cron — глобальный или на каждое устройство |
| **Параллельные бэкапы** | ThreadPoolExecutor, настраиваемое кол-во воркеров |
| **ICMP ping** | Фоновый sweep, live-статус на дашборде |
| **Уведомления** | Webhook для Rocket.Chat / Mattermost / Slack с опциональным git diff |
| **Аутентификация** | Локальные пользователи (bcrypt) + LDAP / Active Directory |
| **Управление пользователями** | Панель администратора: роли, смена пароля, вкл/выкл, удаление |
| **i18n** | Русский / Английский язык (переключение в боковой панели) |
| **systemd-сервис** | Включён `dumper.service` |

---

## Поддерживаемые типы устройств (через Netmiko)

`cisco_ios`, `cisco_xr`, `cisco_nxos`, `cisco_asa`, `juniper_junos`,
`arista_eos`, `huawei`, `hp_comware`, `mikrotik_routeros` и все остальные
[платформы Netmiko](https://github.com/ktbyers/netmiko#supported-platforms).

---

## Быстрый старт (Replit / разработка)

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Запустить приложение
python main.py
# → Открыть http://localhost:5000
```

При первом запуске:
1. Мастер-ключ шифрования **генерируется автоматически** и записывается в `config.yaml` — сделайте резервную копию!
2. Перейдите на `/setup` и создайте первую учётную запись администратора.

---

## Production-развёртывание (Linux / systemd)

```bash
# Создать выделенного пользователя
sudo useradd -r -s /bin/false -d /opt/dumper dumper

# Развернуть файлы приложения
sudo mkdir -p /opt/dumper
sudo cp -r . /opt/dumper/
sudo chown -R dumper:dumper /opt/dumper

# Создать Python venv
sudo -u dumper python3 -m venv /opt/dumper/venv
sudo -u dumper /opt/dumper/venv/bin/pip install -r /opt/dumper/requirements.txt

# Настроить (указать master_key и secret_key)
sudo vim /opt/dumper/config.yaml

# Установить и запустить сервис
sudo cp dumper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dumper

# Проверить статус
sudo systemctl status dumper
sudo journalctl -u dumper -f
```

---

## Структура проекта

```
dumper/
├── main.py                     # Точка входа — FastAPI application factory
├── config.yaml                 # Конфигурация (редактировать этот файл!)
├── requirements.txt
├── dumper.service              # systemd unit
│
├── app/
│   ├── auth.py                 # Аутентификация: bcrypt, LDAP, сессии
│   ├── config.py               # Загрузчик настроек (Pydantic)
│   ├── crypto.py               # AES-256-GCM шифрование/дешифрование
│   ├── database.py             # SQLAlchemy engine + сессии
│   ├── models.py               # ORM-модели (User, Device, BackupJob и др.)
│   ├── i18n.py                 # Переводы RU/EN
│   ├── backup_engine.py        # SSH/Telnet бэкап через Netmiko
│   ├── ping_engine.py          # Параллельный ICMP-sweep
│   ├── git_manager.py          # Git-версионирование через GitPython
│   ├── scheduler.py            # APScheduler cron-задания
│   ├── notifications.py        # Webhook-диспетчер
│   └── routes/
│       ├── auth_routes.py      # /setup, /login, /logout, /set-lang, /set-theme
│       ├── dashboard.py        # / — дашборд (статус устройств, последние бэкапы)
│       ├── inventory.py        # /inventory/ — управление устройствами
│       ├── templates_routes.py # /templates/ — шаблоны команд
│       ├── diff_viewer.py      # /diff/ — просмотр диффов и снимков конфигурации
│       ├── settings.py         # /settings/ — вебхуки, планировщик, LDAP
│       └── users.py            # /users/ — управление пользователями (только admin)
│
├── templates/                  # Jinja2 HTML-шаблоны
│   ├── base.html               # Базовый layout (сайдбар, навигация, адаптив)
│   ├── login.html
│   ├── setup.html
│   ├── dashboard.html
│   ├── inventory.html
│   ├── device_form.html
│   ├── device_jobs.html
│   ├── groups.html
│   ├── templates_list.html
│   ├── template_form.html
│   ├── diff_viewer.html
│   ├── settings.html
│   └── users.html              # Панель управления пользователями
│
├── static/
│   ├── css/style.css           # Metro UI дизайн-система
│   └── js/main.js
│
├── data/                       # SQLite база данных (создаётся автоматически)
│   └── dumper.db
└── configs_repo/               # Git-репозиторий конфигураций (создаётся автоматически)
```

---

## Конфигурация (`config.yaml`)

```yaml
app:
  secret_key: "your-long-random-secret"   # Подпись сессий
  port: 5000
  timezone: "Europe/Moscow"
  debug: false

encryption:
  master_key: "your-base64-32byte-key"    # КРИТИЧНО — сделайте резервную копию!

scheduler:
  default_cron: "0 3 * * *"   # Ежедневно в 03:00
  max_workers: 20              # Макс. параллельных потоков бэкапа
  ping_interval: 60            # ICMP-sweep каждые 60 секунд

git:
  repo_path: "configs_repo"
  author_name: "Dumper"
  author_email: "dumper@localhost"

database:
  path: "data/dumper.db"
```

---

## Аутентификация и пользователи

### Первоначальная настройка

При первом запуске (когда пользователей нет) приложение перенаправляет на `/setup` для создания учётной записи администратора.

### Типы пользователей

| Тип | Описание |
|---|---|
| **Локальный** | Пароль хранится в SQLite (bcrypt). Создаётся через панель `/users/` |
| **LDAP** | Аутентифицируется через Active Directory / LDAP-сервер. Запись в БД создаётся автоматически при первом входе |

### Роли

| Роль | Доступ |
|---|---|
| **Администратор** | Полный доступ, включая управление пользователями, настройки LDAP |
| **Только чтение** | Просмотр дашборда, устройств, бэкапов; запуск бэкапа запрещён |

### Управление пользователями (`/users/`)

Доступно только администраторам. Позволяет:
- Просматривать всех пользователей (локальных и LDAP)
- Менять роль (администратор / только чтение)
- Изменять пароль (только для локальных пользователей)
- Включать / отключать учётные записи
- Удалять пользователей (нельзя удалить себя)

### LDAP-настройка

В разделе **Настройки → LDAP** укажите:
- Адрес сервера и порт
- Base DN и Bind DN
- Фильтр поиска (например: `(sAMAccountName={username})`)
- Флаг SSL/TLS

При успешном LDAP-входе пользователь автоматически появляется в панели `/users/` с типом «ldap».

---

## Diff Viewer (`/diff/`)

- **Клик по коммиту** — просмотр полного снимка конфигурации на момент коммита (активный коммит подсвечивается фиолетовым)
- **Сравнение** — раскройте секцию «сравнить ↕», выберите два коммита и нажмите «сравнить»
- Поддерживается до 50 коммитов в истории на устройство

---

## Безопасность

- **Мастер-ключ**: если вы потеряете `encryption.master_key`, все сохранённые учётные данные устройств станут нечитаемы. Обязательно сделайте резервную копию (HashiCorp Vault, менеджер секретов и т.д.).
- **Ротация ключа**: используйте `crypto.rotate_key()` для повторного шифрования при смене ключа.
- **HTTPS**: в продакшене разместите Dumper за nginx/Caddy с TLS.
- **systemd**: включённый `dumper.service` использует `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`.
- **Сессии**: 8 часов; подписаны `secret_key` из `config.yaml`.

---

## Лицензия

MIT — используйте и адаптируйте свободно.
