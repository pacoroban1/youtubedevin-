#!/usr/bin/env bash
set -euo pipefail

# Ubuntu 22.04 VM bootstrap for the Amharic Recap Autopilot stack.
# Run as root: sudo bash infra/gcp/setup_vm.sh

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "ERROR: run as root (use: sudo bash infra/gcp/setup_vm.sh)" >&2
  exit 1
fi

APP_USER="${APP_USER:-autopilot}"
APP_DIR="${APP_DIR:-/opt/amharic-recap-autopilot}"
ALLOW_IP_CIDR="${ALLOW_IP_CIDR:-}" # optional, e.g. "1.2.3.4/32"

echo "setup: apt packages"
apt-get update -y
apt-get install -y ca-certificates curl gnupg git ufw

if ! command -v docker >/dev/null 2>&1; then
  echo "setup: docker"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "setup: app user (${APP_USER})"
if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "${APP_USER}"
fi
usermod -aG docker "${APP_USER}"

echo "setup: app dir (${APP_DIR})"
mkdir -p "${APP_DIR}" "${APP_DIR}/shared" "${APP_DIR}/state" "${APP_DIR}/repo"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 0755 "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}/shared" "${APP_DIR}/state" "${APP_DIR}/repo"
chmod 0700 "${APP_DIR}/shared" "${APP_DIR}/state"
chmod 0755 "${APP_DIR}/repo"

echo "setup: ufw"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null

# Optional: reverse proxy ports (Caddy/Nginx).
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null

if [[ -n "${ALLOW_IP_CIDR}" ]]; then
  ufw allow from "${ALLOW_IP_CIDR}" to any port 5678 proto tcp >/dev/null
  ufw allow from "${ALLOW_IP_CIDR}" to any port 8000 proto tcp >/dev/null
else
  # NOTE: open to the internet unless restricted by GCP firewall rules.
  ufw allow 5678/tcp >/dev/null
  ufw allow 8000/tcp >/dev/null
fi

ufw --force enable >/dev/null

echo "ok: setup complete"
echo "next: create ${APP_DIR}/shared/.env (chmod 600) and deploy a tag"
