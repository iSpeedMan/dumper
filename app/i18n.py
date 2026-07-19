"""
i18n.py — Простая система переводов (RU / EN).
Используется в шаблонах через глобальную функцию t(key, lang).
Язык берётся из cookie 'lang' (по умолчанию 'ru').
"""

from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # --- Navigation ---
    "nav.dashboard":    {"ru": "дашборд",     "en": "dashboard"},
    "nav.inventory":    {"ru": "устройства",  "en": "inventory"},
    "nav.templates":    {"ru": "шаблоны",     "en": "templates"},
    "nav.settings":     {"ru": "настройки",   "en": "settings"},
    "nav.logout":       {"ru": "выйти",       "en": "logout"},

    # --- Dashboard ---
    "dash.title":           {"ru": "дашборд",              "en": "dashboard"},
    "dash.total":           {"ru": "всего устройств",      "en": "total devices"},
    "dash.online":          {"ru": "онлайн",               "en": "online"},
    "dash.offline":         {"ru": "офлайн",               "en": "offline"},
    "dash.unknown":         {"ru": "неизвестно",           "en": "unknown"},
    "dash.backups_24h":     {"ru": "бэкапов за 24ч",       "en": "backups 24h"},
    "dash.errors_24h":      {"ru": "ошибок за 24ч",        "en": "errors 24h"},
    "dash.device_status":   {"ru": "состояние устройств",  "en": "device status"},
    "dash.recent_backups":  {"ru": "последние бэкапы",     "en": "recent backups"},
    "dash.all_devices":     {"ru": "все устройства →",     "en": "all devices →"},
    "dash.no_devices":      {"ru": "устройства не добавлены.", "en": "no devices added."},
    "dash.add_device":      {"ru": "добавить устройство",  "en": "add device"},
    "dash.no_backups":      {"ru": "бэкапов ещё не было.", "en": "no backups yet."},
    "dash.refresh":         {"ru": "обновить",             "en": "refresh"},
    "dash.group":           {"ru": "группа",               "en": "group"},
    "dash.last_ping":       {"ru": "последний ping",       "en": "last ping"},
    "dash.device":          {"ru": "устройство",           "en": "device"},
    "dash.status":          {"ru": "статус",               "en": "status"},
    "dash.duration":        {"ru": "длит.",                "en": "dur."},
    "dash.time":            {"ru": "время",                "en": "time"},

    # --- Inventory ---
    "inv.title":            {"ru": "устройства",            "en": "inventory"},
    "inv.add":              {"ru": "+ добавить устройство", "en": "+ add device"},
    "inv.groups":           {"ru": "группы",                "en": "groups"},
    "inv.search":           {"ru": "поиск…",                "en": "search…"},
    "inv.name":             {"ru": "имя",                   "en": "name"},
    "inv.host":             {"ru": "хост",                  "en": "host"},
    "inv.type":             {"ru": "тип",                   "en": "type"},
    "inv.group":            {"ru": "группа",                "en": "group"},
    "inv.status":           {"ru": "статус",                "en": "status"},
    "inv.cron":             {"ru": "cron",                  "en": "cron"},
    "inv.backup":           {"ru": "бэкап",                 "en": "backup"},
    "inv.last_change":      {"ru": "последнее изменение",   "en": "last change"},
    "inv.actions":          {"ru": "действия",              "en": "actions"},
    "inv.no_devices":       {"ru": "устройства не добавлены.", "en": "no devices added."},
    "inv.add_first":        {"ru": "добавить первое устройство", "en": "add first device"},
    "inv.edit":             {"ru": "изменить",              "en": "edit"},
    "inv.jobs":             {"ru": "задания",               "en": "jobs"},
    "inv.diff":             {"ru": "diff",                  "en": "diff"},
    "inv.run":              {"ru": "запуск",                "en": "run"},
    "inv.delete":           {"ru": "удалить",               "en": "delete"},
    "inv.confirm_delete":   {"ru": "удалить устройство",    "en": "delete device"},
    "inv.default_cron":     {"ru": "по умолчанию",          "en": "default"},
    "inv.never":            {"ru": "никогда",               "en": "never"},

    # --- Device form ---
    "dev.add_title":        {"ru": "добавить устройство",   "en": "add device"},
    "dev.edit_title":       {"ru": "изменить устройство",   "en": "edit device"},
    "dev.name":             {"ru": "имя устройства",        "en": "device name"},
    "dev.host":             {"ru": "хост / ip",             "en": "host / ip"},
    "dev.port":             {"ru": "порт",                  "en": "port"},
    "dev.protocol":         {"ru": "протокол",              "en": "protocol"},
    "dev.netmiko_type":     {"ru": "тип netmiko",           "en": "netmiko type"},
    "dev.credentials":      {"ru": "учётные данные",        "en": "credentials"},
    "dev.username":         {"ru": "логин",                 "en": "username"},
    "dev.password":         {"ru": "пароль",                "en": "password"},
    "dev.password_hint":    {"ru": "(оставьте пустым — без изменений)", "en": "(leave blank to keep current)"},
    "dev.enable_secret":    {"ru": "enable secret (необяз.)", "en": "enable secret (optional)"},
    "dev.backup_config":    {"ru": "конфигурация бэкапа",   "en": "backup config"},
    "dev.group":            {"ru": "группа",                "en": "group"},
    "dev.no_group":         {"ru": "— без группы —",        "en": "— no group —"},
    "dev.template":         {"ru": "шаблон команд",         "en": "command template"},
    "dev.no_template":      {"ru": "— без шаблона —",       "en": "— no template —"},
    "dev.custom_cron":      {"ru": "custom cron (пусто = глобальный)", "en": "custom cron (blank = global)"},
    "dev.cron_hint":        {"ru": "формат: минута час день месяц день_недели", "en": "format: minute hour day month weekday"},
    "dev.backup_enabled":   {"ru": "бэкап включён",         "en": "backup enabled"},
    "dev.description":      {"ru": "описание",              "en": "description"},
    "dev.save":             {"ru": "сохранить",             "en": "save"},
    "dev.cancel":           {"ru": "отмена",                "en": "cancel"},
    "dev.back":             {"ru": "← назад",               "en": "← back"},

    # --- Templates ---
    "tpl.title":            {"ru": "шаблоны команд",        "en": "command templates"},
    "tpl.add":              {"ru": "добавить шаблон",     "en": "add template"},
    "tpl.name":             {"ru": "название",              "en": "name"},
    "tpl.device_type":      {"ru": "тип устройства",        "en": "device type"},
    "tpl.description":      {"ru": "описание",              "en": "description"},
    "tpl.commands_count":   {"ru": "команд",                "en": "commands"},
    "tpl.actions":          {"ru": "действия",              "en": "actions"},
    "tpl.no_templates":     {"ru": "шаблоны не созданы.",   "en": "no templates yet."},
    "tpl.create_first":     {"ru": "создать первый шаблон", "en": "create first template"},
    "tpl.edit":             {"ru": "изменить",              "en": "edit"},
    "tpl.delete":           {"ru": "удалить",               "en": "delete"},
    "tpl.add_title":        {"ru": "добавить шаблон",       "en": "add template"},
    "tpl.edit_title":       {"ru": "изменить шаблон",       "en": "edit template"},
    "tpl.commands":         {"ru": "команды (по одной на строке)", "en": "commands (one per line)"},
    "tpl.commands_hint":    {"ru": "строки с # — комментарии; 'enable' — режим привилегий", "en": "lines with # are comments; 'enable' enters privileged mode"},
    "tpl.save":             {"ru": "сохранить",             "en": "save"},
    "tpl.cancel":           {"ru": "отмена",                "en": "cancel"},
    "tpl.back":             {"ru": "← назад",               "en": "← back"},

    # --- Settings ---
    "set.title":            {"ru": "настройки",             "en": "settings"},
    "set.webhooks":         {"ru": "webhooks уведомлений",  "en": "notification webhooks"},
    "set.add_webhook":      {"ru": "добавить webhook",      "en": "add webhook"},
    "set.webhook_name":     {"ru": "название",              "en": "name"},
    "set.webhook_url":      {"ru": "url",                   "en": "url"},
    "set.on_backup_fail":   {"ru": "ошибки бэкапа",         "en": "backup failures"},
    "set.on_ping_fail":     {"ru": "устройство недоступно", "en": "device unreachable"},
    "set.send_diff":        {"ru": "отправлять git diff",   "en": "include git diff"},
    "set.no_webhooks":      {"ru": "webhooks не настроены.", "en": "no webhooks configured."},
    "set.add":              {"ru": "добавить",              "en": "add"},
    "set.toggle":           {"ru": "вкл/выкл",              "en": "toggle"},
    "set.delete":           {"ru": "удалить",               "en": "delete"},
    "set.scheduler":        {"ru": "планировщик задач",     "en": "scheduler jobs"},
    "set.job_id":           {"ru": "id",                    "en": "id"},
    "set.job_name":         {"ru": "задача",                "en": "task"},
    "set.next_run":         {"ru": "следующий запуск",      "en": "next run"},
    "set.no_jobs":          {"ru": "планировщик не запущен или задач нет.", "en": "scheduler not running or no jobs."},
    "set.active":           {"ru": "активен",               "en": "active"},
    "set.disabled":         {"ru": "отключён",              "en": "disabled"},
    "set.triggers":         {"ru": "триггеры",              "en": "triggers"},
    "set.save":             {"ru": "сохранить",             "en": "save"},
    "set.backup_schedule":  {"ru": "расписание по умолчанию",    "en": "default backup schedule"},
    "set.backup_cron":      {"ru": "cron-выражение",        "en": "cron expression"},
    "set.backup_cron_hint": {"ru": "5 полей: минута час день месяц день_недели. Пример: 0 3 * * * = ежедневно в 03:00", "en": "5 fields: minute hour day month weekday. Example: 0 3 * * * = daily at 03:00"},
    "set.cron_invalid":     {"ru": "недопустимое cron-выражение (ожидается 5 полей)", "en": "invalid cron expression (5 fields expected)"},

    # --- LDAP ---
    "ldap.title":           {"ru": "ldap аутентификация",   "en": "ldap authentication"},
    "ldap.enabled":         {"ru": "включить ldap",         "en": "enable ldap"},
    "ldap.server":          {"ru": "сервер",                "en": "server"},
    "ldap.port":            {"ru": "порт",                  "en": "port"},
    "ldap.use_ssl":         {"ru": "использовать ssl/tls",  "en": "use ssl/tls"},
    "ldap.base_dn":         {"ru": "base dn",               "en": "base dn"},
    "ldap.bind_dn":         {"ru": "bind dn",               "en": "bind dn"},
    "ldap.bind_password":   {"ru": "bind пароль",           "en": "bind password"},
    "ldap.filter":          {"ru": "фильтр поиска",         "en": "search filter"},
    "ldap.save":            {"ru": "сохранить настройки ldap", "en": "save ldap settings"},
    "ldap.test":            {"ru": "тест подключения",      "en": "test connection"},
    "ldap.hint":            {"ru": "используйте {username} в фильтре", "en": "use {username} in filter"},

    # --- Auth ---
    "auth.login_title":     {"ru": "вход в систему",        "en": "sign in"},
    "auth.username":        {"ru": "имя пользователя",      "en": "username"},
    "auth.password":        {"ru": "пароль",                "en": "password"},
    "auth.sign_in":         {"ru": "войти",                 "en": "sign in"},
    "auth.or_ldap":         {"ru": "или войти через ldap",  "en": "or sign in via ldap"},
    "auth.wrong_creds":     {"ru": "неверный логин или пароль", "en": "invalid username or password"},
    "auth.setup_title":     {"ru": "первоначальная настройка", "en": "initial setup"},
    "auth.setup_desc":      {"ru": "создайте учётную запись администратора", "en": "create an administrator account"},
    "auth.create_admin":    {"ru": "создать администратора", "en": "create administrator"},
    "auth.logged_in_as":    {"ru": "вы вошли как",          "en": "signed in as"},

    # --- Jobs ---
    "job.title":            {"ru": "история бэкапов",       "en": "backup history"},
    "job.id":               {"ru": "#",                     "en": "#"},
    "job.status":           {"ru": "статус",                "en": "status"},
    "job.started":          {"ru": "запущен",               "en": "started"},
    "job.duration":         {"ru": "длит.",                 "en": "dur."},
    "job.commit":           {"ru": "коммит",                "en": "commit"},
    "job.trigger":          {"ru": "инициатор",             "en": "trigger"},
    "job.error":            {"ru": "ошибка",                "en": "error"},
    "job.no_jobs":          {"ru": "бэкапов ещё не было.",  "en": "no backups yet."},
    "job.run_now":          {"ru": "запустить сейчас",      "en": "run now"},
    "job.back_inventory":   {"ru": "← инвентарь",          "en": "← inventory"},
    "job.diff_viewer":      {"ru": "diff viewer",           "en": "diff viewer"},

    # --- Diff ---
    "diff.title":           {"ru": "diff viewer",           "en": "diff viewer"},
    "diff.commit_history":  {"ru": "история коммитов",      "en": "commit history"},
    "diff.commit_a":        {"ru": "коммит a (старый)",     "en": "commit a (older)"},
    "diff.commit_b":        {"ru": "коммит b (новый)",      "en": "commit b (newer)"},
    "diff.compare":         {"ru": "сравнить",              "en": "compare"},
    "diff.no_commits":      {"ru": "коммитов нет.",         "en": "no commits yet."},
    "diff.current_config":  {"ru": "текущий конфиг",        "en": "current config"},
    "diff.no_config":       {"ru": "конфиг ещё не снимался.", "en": "no config yet."},
    "diff.vs":              {"ru": "→",                     "en": "→"},
    "diff.view_commit":     {"ru": "снимок коммита",        "en": "commit snapshot"},

    # --- Users ---
    "nav.users":            {"ru": "пользователи",          "en": "users"},
    "usr.title":            {"ru": "пользователи",          "en": "users"},
    "usr.add":              {"ru": "добавить пользователя", "en": "add user"},
    "usr.username":         {"ru": "имя пользователя",      "en": "username"},
    "usr.role":             {"ru": "роль",                   "en": "role"},
    "usr.type":             {"ru": "тип",                    "en": "type"},
    "usr.status":           {"ru": "статус",                 "en": "status"},
    "usr.last_login":       {"ru": "последний вход",         "en": "last login"},
    "usr.created":          {"ru": "создан",                 "en": "created"},
    "usr.actions":          {"ru": "действия",               "en": "actions"},
    "usr.admin":            {"ru": "администратор",          "en": "admin"},
    "usr.readonly":         {"ru": "только чтение",          "en": "read-only"},
    "usr.local":            {"ru": "локальный",              "en": "local"},
    "usr.ldap":             {"ru": "ldap",                   "en": "ldap"},
    "usr.active":           {"ru": "активен",                "en": "active"},
    "usr.inactive":         {"ru": "отключён",               "en": "inactive"},
    "usr.change_role":      {"ru": "сменить роль",           "en": "change role"},
    "usr.change_password":  {"ru": "сменить пароль",         "en": "change password"},
    "usr.new_password":     {"ru": "новый пароль",           "en": "new password"},
    "usr.password_hint":    {"ru": "мин. 6 символов",        "en": "min 6 characters"},
    "usr.toggle_active":    {"ru": "вкл / выкл",             "en": "enable / disable"},
    "usr.delete":           {"ru": "удалить",                "en": "delete"},
    "usr.confirm_delete":   {"ru": "удалить пользователя",   "en": "delete user"},
    "usr.no_users":         {"ru": "пользователей нет.",     "en": "no users."},

    # --- Groups ---
    "grp.title":            {"ru": "группы устройств",      "en": "device groups"},
    "grp.add":              {"ru": "добавить группу",       "en": "add group"},
    "grp.name":             {"ru": "название",              "en": "name"},
    "grp.description":      {"ru": "описание",              "en": "description"},
    "grp.count":            {"ru": "устройств",             "en": "devices"},
    "grp.no_groups":        {"ru": "групп ещё нет.",        "en": "no groups yet."},
    "grp.add_btn":          {"ru": "добавить",              "en": "add"},
    "grp.delete":           {"ru": "удалить",               "en": "delete"},
    "grp.back":             {"ru": "← инвентарь",          "en": "← inventory"},

    # --- Common status ---
    "status.online":        {"ru": "онлайн",    "en": "online"},
    "status.offline":       {"ru": "офлайн",    "en": "offline"},
    "status.unknown":       {"ru": "неизвестно","en": "unknown"},
    "status.success":       {"ru": "успешно",   "en": "success"},
    "status.failed":        {"ru": "ошибка",    "en": "failed"},
    "status.running":       {"ru": "выполняется","en": "running"},
    "status.pending":       {"ru": "ожидание",  "en": "pending"},
    "status.skipped":       {"ru": "пропущен",  "en": "skipped"},
    "status.never":         {"ru": "никогда",   "en": "never"},
    "status.na":            {"ru": "—",         "en": "—"},
}


def t(key: str, lang: str = "ru") -> str:
    """Возвращает перевод строки по ключу для заданного языка."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key  # Fallback: показать ключ
    return entry.get(lang) or entry.get("ru") or key


def make_translator(lang: str):
    """Возвращает функцию-переводчик для конкретного языка (для Jinja2 globals)."""
    def _t(key: str) -> str:
        return t(key, lang)
    return _t
