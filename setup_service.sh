#!/usr/bin/env bash
# Sets up a systemd user service so Dead Air starts on boot.
# Run as the radio user — no sudo required.
set -euo pipefail

# -------------------- COLOURS --------------------
if [ -t 1 ]; then
    BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
    GREEN='\033[32m'; YELLOW='\033[33m'; CYAN='\033[36m'
    BRIGHT_GREEN='\033[92m'; BRIGHT_CYAN='\033[96m'; BRIGHT_YELLOW='\033[93m'
else
    BOLD=''; DIM=''; RESET=''
    GREEN=''; YELLOW=''; CYAN=''
    BRIGHT_GREEN=''; BRIGHT_CYAN=''; BRIGHT_YELLOW=''
fi

step() { printf "${BOLD}${BRIGHT_CYAN}==> ${1}${RESET}\n"; }
ok()   { printf "    ${BOLD}${GREEN}✓ ${1}${RESET}\n"; }
info() { printf "    ${DIM}${1}${RESET}\n"; }
warn() { printf "    ${BOLD}${BRIGHT_YELLOW}! ${1}${RESET}\n"; }
# -------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
SERVICE_NAME="deadair"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/${SERVICE_NAME}.service"

if [ ! -x "${VENV_PYTHON}" ]; then
    printf "${BOLD}\033[31mERROR:${RESET} venv not found at ${VENV_PYTHON}\n"
    printf "Run install.sh first.\n"
    exit 1
fi

step "Creating service directory..."
mkdir -p "${SERVICE_DIR}"
ok "${SERVICE_DIR}"

step "Writing ${SERVICE_FILE}..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Dead Air FM radio simulator
After=pipewire.service pipewire-pulse.service sound.target
Wants=pipewire.service pipewire-pulse.service

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_PYTHON} ${SCRIPT_DIR}/play_radio.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
ok "Service file written."

step "Reloading systemd user daemon..."
systemctl --user daemon-reload
ok "Done."

step "Enabling service (start on login/boot)..."
systemctl --user enable "${SERVICE_NAME}"
ok "Enabled."

# Enable linger so the user service starts at boot without a login session.
step "Enabling linger for ${USER}..."
if loginctl enable-linger "${USER}" 2>/dev/null; then
    ok "Linger enabled — service will start at boot."
elif sudo loginctl enable-linger "${USER}" 2>/dev/null; then
    ok "Linger enabled (via sudo) — service will start at boot."
else
    warn "Could not enable linger. The service will only start when ${USER} logs in."
    warn "To fix: run 'sudo loginctl enable-linger ${USER}'"
fi

step "Starting service now..."
systemctl --user start "${SERVICE_NAME}"
ok "Started."

printf "\n${BOLD}${BRIGHT_GREEN}✓ Dead Air service installed and running.${RESET}\n\n"
printf "${BOLD}Useful commands:${RESET}\n"
printf "  ${DIM}systemctl --user status ${SERVICE_NAME}${RESET}\n"
printf "  ${DIM}systemctl --user stop ${SERVICE_NAME}${RESET}\n"
printf "  ${DIM}systemctl --user restart ${SERVICE_NAME}${RESET}\n"
printf "  ${DIM}journalctl --user -u ${SERVICE_NAME} -f${RESET}\n\n"
