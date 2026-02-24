#!/usr/bin/env bash
set -euo pipefail

# ---------------- CONFIG ----------------
RADIO_USER="${SUDO_USER:-$USER}"
HOME_DIR="$(getent passwd "$RADIO_USER" | cut -d: -f6)"
PROJECT_DIR="${HOME_DIR}/radio-code"
VENV_DIR="${PROJECT_DIR}/.venv"
# ---------------------------------------

echo "==> Using user: ${RADIO_USER}"
echo "==> Home dir: ${HOME_DIR}"
echo "==> Project dir: ${PROJECT_DIR}"

echo "==> Installing system packages..."
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  mpv libmpv2 ffmpeg \
  alsa-utils \
  pipewire pipewire-pulse wireplumber \
  pulseaudio-utils \
  git ca-certificates

echo "==> Adding ${RADIO_USER} to useful groups (audio, gpio, input)..."
sudo usermod -aG audio,gpio,input "${RADIO_USER}" || true

echo "==> Creating project directory..."
sudo -u "${RADIO_USER}" mkdir -p "${PROJECT_DIR}"

echo "==> Creating Python venv with system site-packages..."
sudo -u "${RADIO_USER}" python3 -m venv --system-site-packages "${VENV_DIR}"

echo "==> Upgrading pip/setuptools/wheel in venv..."
sudo -u "${RADIO_USER}" "${VENV_DIR}/bin/python" -m pip install --upgrade \
  pip setuptools wheel

echo "==> Installing Python deps in venv..."
sudo -u "${RADIO_USER}" "${VENV_DIR}/bin/pip" install --upgrade \
  python-mpv mutagen \
  gpiozero lgpio toml \
  fastapi "uvicorn[standard]"

echo "==> Sanity checks..."

echo "--- mpv ---"
mpv --version | head -n 2 || true

echo "--- libmpv ---"
ldconfig -p | grep -E 'libmpv\.so|libmpv\.so\.' || true

echo "--- python imports (venv) ---"
sudo -u "${RADIO_USER}" "${VENV_DIR}/bin/python" - <<'PY'
import sys
import mpv
import mutagen
import gpiozero
import lgpio
print("python:", sys.version)
print("python-mpv OK")
print("mutagen:", mutagen.version_string)
print("gpiozero:", gpiozero.__version__)
print("lgpio OK")
PY

echo
echo "==> Done."
echo
echo "IMPORTANT:"
echo "  • Log out/in or reboot so group changes apply."
echo "  • Run everything WITHOUT sudo."
echo
echo "Next steps:"
echo "  cd ${PROJECT_DIR}"
echo "  . .venv/bin/activate"
echo "  python -m radio.scan_media --help"
echo "  python -m radio.radio"
