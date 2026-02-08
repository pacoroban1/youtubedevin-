#!/usr/bin/env bash
set -euo pipefail

# Local helper: SSH into a GCP VM and run the deploy/health scripts there.
#
# Requires:
#   - gcloud CLI installed + authenticated
#   - env vars: GCP_PROJECT, GCP_ZONE, GCP_VM
#
# Optional env vars:
#   GCP_SSH_USER=autopilot
#   GCP_APP_DIR=/opt/amharic-recap-autopilot
#   REPO_URL=https://github.com/pacoroban1/youtubedevin-.git
#   ENABLE_CADDY=0|1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'USAGE'
Usage:
  bash infra/gcp/remote.sh promote  --tag <TAG>
  bash infra/gcp/remote.sh rollback [--tag <TAG>]
  bash infra/gcp/remote.sh health

Environment (required):
  GCP_PROJECT=...
  GCP_ZONE=...
  GCP_VM=...        (instance name)

Environment (optional):
  GCP_SSH_USER=autopilot
  GCP_APP_DIR=/opt/amharic-recap-autopilot
  REPO_URL=https://github.com/pacoroban1/youtubedevin-.git
  ENABLE_CADDY=0|1
USAGE
}

cmd="${1:-}"
shift || true

TAG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${cmd}" ]]; then
  usage >&2
  exit 2
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud CLI not found (install Google Cloud SDK)." >&2
  exit 1
fi

: "${GCP_PROJECT:?ERROR: set GCP_PROJECT}"
: "${GCP_ZONE:?ERROR: set GCP_ZONE}"
: "${GCP_VM:?ERROR: set GCP_VM}"

GCP_SSH_USER="${GCP_SSH_USER:-autopilot}"
GCP_APP_DIR="${GCP_APP_DIR:-/opt/amharic-recap-autopilot}"
REPO_URL="${REPO_URL:-https://github.com/pacoroban1/youtubedevin-.git}"
ENABLE_CADDY="${ENABLE_CADDY:-0}"

ssh_target="${GCP_SSH_USER}@${GCP_VM}"

q() { printf "%q" "$1"; }

ensure_tag_on_remote() {
  local tag="$1"
  if [[ -z "${tag}" ]]; then
    echo "ERROR: --tag is required" >&2
    exit 2
  fi
  if ! git ls-remote --tags "${REPO_URL}" "refs/tags/${tag}" | grep -q .; then
    echo "ERROR: tag not found on remote (${REPO_URL}): ${tag}" >&2
    echo "Run: TAG=${tag} make release" >&2
    exit 1
  fi
}

remote_common_prefix() {
  cat <<'BASH'
set -euo pipefail
if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not found on VM" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found on VM (run setup_vm.sh first)" >&2
  exit 1
fi
BASH
}

remote_promote_cmd() {
  local tag="$1"
  local app_dir="$2"
  local repo_url="$3"
  local enable_caddy="$4"

  cat <<BASH
$(remote_common_prefix)
APP_DIR=$(q "${app_dir}")
REPO_URL=$(q "${repo_url}")
TAG=$(q "${tag}")
ENABLE_CADDY=$(q "${enable_caddy}")

if [[ ! -d "\${APP_DIR}" ]]; then
  echo "ERROR: missing \${APP_DIR} (run: sudo bash infra/gcp/setup_vm.sh)" >&2
  exit 1
fi

mkdir -p "\${APP_DIR}/repo"
if [[ ! -d "\${APP_DIR}/repo/.git" ]]; then
  echo "remote: git clone"
  git clone "\${REPO_URL}" "\${APP_DIR}/repo"
fi

cd "\${APP_DIR}/repo"
git fetch --tags --prune
git checkout -f "tags/\${TAG}" >/dev/null

APP_DIR="\${APP_DIR}" REPO_URL="\${REPO_URL}" ENABLE_CADDY="\${ENABLE_CADDY}" \\
  bash infra/gcp/deploy.sh --tag "\${TAG}" --app-dir "\${APP_DIR}" --repo-url "\${REPO_URL}"
BASH
}

remote_rollback_cmd() {
  local tag="$1"
  local app_dir="$2"
  local repo_url="$3"
  local enable_caddy="$4"

  local deploy_args=(--rollback --app-dir "${app_dir}" --repo-url "${repo_url}")
  if [[ -n "${tag}" ]]; then
    deploy_args=(--rollback --tag "${tag}" --app-dir "${app_dir}" --repo-url "${repo_url}")
  fi

  cat <<BASH
$(remote_common_prefix)
APP_DIR=$(q "${app_dir}")
REPO_URL=$(q "${repo_url}")
ENABLE_CADDY=$(q "${enable_caddy}")

if [[ ! -d "\${APP_DIR}/repo/.git" ]]; then
  echo "ERROR: repo not initialized on VM (promote at least once first)" >&2
  exit 1
fi

cd "\${APP_DIR}/repo"
git fetch --tags --prune

APP_DIR="\${APP_DIR}" REPO_URL="\${REPO_URL}" ENABLE_CADDY="\${ENABLE_CADDY}" \\
  bash infra/gcp/deploy.sh $(printf "%q " "${deploy_args[@]}")
BASH
}

remote_health_cmd() {
  local app_dir="$1"
  cat <<BASH
set -euo pipefail
APP_DIR=$(q "${app_dir}")
if [[ ! -d "\${APP_DIR}/repo/.git" ]]; then
  echo "ERROR: repo not initialized on VM" >&2
  exit 1
fi
cd "\${APP_DIR}/repo"
bash infra/gcp/healthcheck.sh
BASH
}

case "${cmd}" in
  promote)
    ensure_tag_on_remote "${TAG}"
    remote_cmd="$(remote_promote_cmd "${TAG}" "${GCP_APP_DIR}" "${REPO_URL}" "${ENABLE_CADDY}")"
    gcloud compute ssh "${ssh_target}" --project "${GCP_PROJECT}" --zone "${GCP_ZONE}" --command "bash -lc $(q "${remote_cmd}")"
    ;;
  rollback)
    if [[ -n "${TAG}" ]]; then
      ensure_tag_on_remote "${TAG}"
    fi
    remote_cmd="$(remote_rollback_cmd "${TAG}" "${GCP_APP_DIR}" "${REPO_URL}" "${ENABLE_CADDY}")"
    gcloud compute ssh "${ssh_target}" --project "${GCP_PROJECT}" --zone "${GCP_ZONE}" --command "bash -lc $(q "${remote_cmd}")"
    ;;
  health)
    remote_cmd="$(remote_health_cmd "${GCP_APP_DIR}")"
    gcloud compute ssh "${ssh_target}" --project "${GCP_PROJECT}" --zone "${GCP_ZONE}" --command "bash -lc $(q "${remote_cmd}")"
    ;;
  *)
    echo "ERROR: unknown command: ${cmd}" >&2
    usage >&2
    exit 2
    ;;
esac

