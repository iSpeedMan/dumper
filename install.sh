#!/usr/bin/env bash
# ==============================================================================
# Dumper — production install script
# Tested on: Debian 12, Ubuntu 22.04/24.04
#
# Usage:
#   sudo bash install.sh
# ==============================================================================
set -euo pipefail

APP_DIR="/opt/dumper"
SERVICE_SRC="dumper.service"
SERVICE_DST="/etc/systemd/system/dumper.service"
APP_USER="dumper"
APP_GROUP="dumper"
PYTHON="python3"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()  { echo -e "${RED}[ERR]${NC} $*" >&2; exit 1; }

# ── Guards ────────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash install.sh"

[[ -f "$APP_DIR/main.py" ]] || \
    die "App not found at $APP_DIR. Clone the repo there first."

[[ -f "$APP_DIR/$SERVICE_SRC" ]] || \
    die "Service file $APP_DIR/$SERVICE_SRC not found."

# ── 1. System user ────────────────────────────────────────────────────────────
echo "==> Creating system user '$APP_USER' ..."
if id "$APP_USER" &>/dev/null; then
    warn "User '$APP_USER' already exists — skipping."
else
    useradd -r -s /sbin/nologin -d "$APP_DIR" "$APP_USER"
    ok "User '$APP_USER' created."
fi

# ── 2. Python venv ────────────────────────────────────────────────────────────
VENV="$APP_DIR/venv"
echo "==> Setting up Python virtual environment ..."
if [[ ! -d "$VENV" ]]; then
    "$PYTHON" -m venv "$VENV"
    ok "venv created at $VENV"
else
    warn "venv already exists — skipping creation."
fi

if [[ -f "$APP_DIR/requirements.txt" ]]; then
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
    ok "Python dependencies installed."
else
    warn "requirements.txt not found — skipping pip install."
fi

# ── 3. Config file ────────────────────────────────────────────────────────────
echo "==> Checking config.yaml ..."
if [[ ! -f "$APP_DIR/config.yaml" ]]; then
    if [[ -f "$APP_DIR/config.yaml.sample" ]]; then
        cp "$APP_DIR/config.yaml.sample" "$APP_DIR/config.yaml"
        warn "config.yaml created from sample — EDIT IT before starting the service!"
        warn "  $APP_DIR/config.yaml"
    else
        warn "config.yaml.sample not found — create config.yaml manually."
    fi
else
    ok "config.yaml already exists."
fi

# ── 4. Data directories and ownership ─────────────────────────────────────────
echo "==> Creating data directories ..."
DATA_DIRS=("$APP_DIR/data" "$APP_DIR/configs_repo")
for d in "${DATA_DIRS[@]}"; do
    mkdir -p "$d"
    ok "Directory: $d"
done

echo "==> Setting ownership to $APP_USER:$APP_GROUP ..."
# Full app dir owned by root (read-only for service) except the writable dirs
chown root:root "$APP_DIR"
chown -R "$APP_USER:$APP_GROUP" "${DATA_DIRS[@]}"
# Config must be readable by the service user
chown root:"$APP_GROUP" "$APP_DIR/config.yaml" 2>/dev/null || true
chmod 640 "$APP_DIR/config.yaml" 2>/dev/null || true
ok "Ownership set."

# ── 5. Git identity for configs_repo ─────────────────────────────────────────
echo "==> Configuring git identity for '$APP_USER' ..."
if ! sudo -u "$APP_USER" git -C "$APP_DIR/configs_repo" config user.email &>/dev/null 2>&1; then
    sudo -u "$APP_USER" git config --global user.email "dumper@$(hostname -f 2>/dev/null || echo localhost)"
    sudo -u "$APP_USER" git config --global user.name "Dumper"
    sudo -u "$APP_USER" git config --global init.defaultBranch main
    ok "Git identity configured for '$APP_USER'."
else
    warn "Git identity already set — skipping."
fi

# ── 6. systemd service ────────────────────────────────────────────────────────
echo "==> Installing systemd service ..."
cp "$APP_DIR/$SERVICE_SRC" "$SERVICE_DST"
chmod 644 "$SERVICE_DST"
systemctl daemon-reload
ok "Service file installed: $SERVICE_DST"

echo "==> Enabling and starting dumper.service ..."
systemctl enable --now dumper
ok "Service enabled and started."

# ── 7. Status ─────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────────────"
systemctl status dumper --no-pager -l || true
echo "────────────────────────────────────────────────────"
echo ""
ok "Dumper installation complete."
echo ""
echo "  Web UI:  http://$(hostname -f 2>/dev/null || hostname):5000"
echo "  Logs:    journalctl -u dumper -f"
echo "  Config:  $APP_DIR/config.yaml"
echo ""
