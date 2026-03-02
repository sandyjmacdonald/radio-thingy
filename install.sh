#!/usr/bin/env bash
set -euo pipefail

# -------------------- COLOURS --------------------
if [ -t 1 ]; then
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    CYAN='\033[36m'
    BRIGHT_GREEN='\033[92m'
    BRIGHT_CYAN='\033[96m'
    BRIGHT_YELLOW='\033[93m'
else
    BOLD=''; DIM=''; RESET=''
    GREEN=''; YELLOW=''; CYAN=''
    BRIGHT_GREEN=''; BRIGHT_CYAN=''; BRIGHT_YELLOW=''
fi

step()  { printf "${BOLD}${BRIGHT_CYAN}==> ${1}${RESET}\n"; }
ok()    { printf "    ${BOLD}${GREEN}✓ ${1}${RESET}\n"; }
info()  { printf "    ${DIM}${1}${RESET}\n"; }
warn()  { printf "    ${BOLD}${BRIGHT_YELLOW}! ${1}${RESET}\n"; }
# -------------------------------------------------

# ---------------- CONFIG ----------------
RADIO_USER="${SUDO_USER:-$USER}"
HOME_DIR="$(getent passwd "$RADIO_USER" | cut -d: -f6)"
PROJECT_DIR="${HOME_DIR}/deadair"
VENV_DIR="${PROJECT_DIR}/.venv"
# ---------------------------------------

step "Configuration"
info "User:        ${RADIO_USER}"
info "Home dir:    ${HOME_DIR}"
info "Project dir: ${PROJECT_DIR}"

step "Installing system packages..."
sudo apt update -qq
sudo apt install -y \
  python3 python3-venv python3-pip \
  mpv libmpv2 ffmpeg \
  alsa-utils \
  pipewire pipewire-pulse wireplumber \
  pulseaudio-utils \
  git ca-certificates
ok "System packages installed."

step "Adding ${RADIO_USER} to groups (audio, gpio, input)..."
sudo usermod -aG audio,gpio,input "${RADIO_USER}" || true
ok "Groups updated."

step "Creating project directory..."
sudo -u "${RADIO_USER}" mkdir -p "${PROJECT_DIR}"
ok "${PROJECT_DIR} ready."

step "Creating Python venv with system site-packages..."
sudo -u "${RADIO_USER}" python3 -m venv --system-site-packages "${VENV_DIR}"
ok "Venv created at ${VENV_DIR}"

step "Upgrading pip / setuptools / wheel..."
sudo -u "${RADIO_USER}" "${VENV_DIR}/bin/python" -m pip install --upgrade \
  pip setuptools wheel -q
ok "Done."

step "Installing Python dependencies..."
sudo -u "${RADIO_USER}" "${VENV_DIR}/bin/pip" install --upgrade \
  python-mpv mutagen \
  gpiozero lgpio toml \
  fastapi "uvicorn[standard]" -q
ok "Python deps installed."

step "Sanity checks..."

printf "\n${BOLD}${CYAN}--- mpv ---${RESET}\n"
mpv --version | head -n 2 || true

printf "\n${BOLD}${CYAN}--- libmpv ---${RESET}\n"
ldconfig -p | grep -E 'libmpv\.so|libmpv\.so\.' || true

printf "\n${BOLD}${CYAN}--- Python imports (venv) ---${RESET}\n"
sudo -u "${RADIO_USER}" "${VENV_DIR}/bin/python" - <<'PY'
import sys
import mpv
import mutagen
import gpiozero
import lgpio
print("  python:", sys.version.split()[0])
print("  python-mpv OK")
print("  mutagen:", mutagen.version_string)
print("  gpiozero OK")
print("  lgpio OK")
PY

printf "\n${BOLD}${BRIGHT_GREEN}✓ Installation complete.${RESET}\n\n"

printf "${BOLD}${BRIGHT_YELLOW}IMPORTANT:${RESET}\n"
printf "  • Log out/in or reboot so group changes apply.\n"
printf "  • Run everything WITHOUT sudo.\n\n"

printf "${BOLD}Next steps:${RESET}\n"
printf "  ${DIM}cd ${PROJECT_DIR}${RESET}\n"
printf "  ${DIM}. .venv/bin/activate${RESET}\n"
printf "  ${DIM}python3 rescan.py${RESET}\n"
printf "  ${DIM}python3 play_radio.py${RESET}\n"
