#!/usr/bin/env bash
set -euo pipefail

# Deploy a specific git tag to a single Compute Engine VM (runner + n8n + postgres).
#
# Expected layout on the VM (created by setup_vm.sh):
#   /opt/amharic-recap-autopilot/
#     repo/        (git clone)
#     shared/.env  (secrets, chmod 600)
#     state/       (deployment state)
#
# Run as the app user (non-root) that is in the docker group.

usage() {
  cat <<'USAGE'
Usage:
  bash infra/gcp/deploy.sh --tag <TAG> [--app-dir /opt/amharic-recap-autopilot] [--repo-url <url>] [--env-file <path>] [--rollback]

Notes:
  - Secrets are stored outside git at: <app-dir>/shared/.env
  - The repo root .env is a symlink to that file.
  - --env-file (optional) copies a local env file into <app-dir>/shared/.env (mode 600).
  - --rollback without --tag deploys the previously deployed tag recorded on the VM.
USAGE
}

APP_DIR="${APP_DIR:-/opt/amharic-recap-autopilot}"
REPO_URL_DEFAULT="https://github.com/pacoroban1/youtubedevin-.git"
REPO_URL="${REPO_URL:-${REPO_URL_DEFAULT}}"
TAG="${TAG:-}"
ROLLBACK=0
ENV_FILE=""
ENABLE_CADDY="${ENABLE_CADDY:-0}" # if 1, uses infra/gcp/docker-compose.caddy.yml

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="$2"
      shift 2
      ;;
    --repo-url)
      REPO_URL="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --rollback)
      ROLLBACK=1
      shift
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

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "ERROR: do not run deploy as root; use the app user (must be in docker group)." >&2
  exit 1
fi

STATE_DIR="${APP_DIR}/state"
SHARED_DIR="${APP_DIR}/shared"
REPO_DIR="${APP_DIR}/repo"
ENV_DST="${SHARED_DIR}/.env"

mkdir -p "${STATE_DIR}" "${SHARED_DIR}" "${REPO_DIR}"
chmod 700 "${STATE_DIR}" "${SHARED_DIR}" || true

if [[ -n "${ENV_FILE}" ]]; then
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: --env-file not found: ${ENV_FILE}" >&2
    exit 1
  fi
  umask 077
  cp -f "${ENV_FILE}" "${ENV_DST}"
  chmod 600 "${ENV_DST}"
fi

if [[ ! -f "${ENV_DST}" ]]; then
  echo "ERROR: missing env file: ${ENV_DST}" >&2
  echo "Create it on the VM (chmod 600) before deploying." >&2
  exit 1
fi

require_env() {
  local key="$1"
  if ! grep -Eq "^${key}=" "${ENV_DST}"; then
    echo "ERROR: missing required env var in ${ENV_DST}: ${key}" >&2
    exit 1
  fi
  local val
  val="$(grep -E "^${key}=" "${ENV_DST}" | head -n 1 | cut -d= -f2- || true)"
  if [[ -z "${val}" ]]; then
    echo "ERROR: required env var is empty in ${ENV_DST}: ${key}" >&2
    exit 1
  fi
}

require_env "GEMINI_API_KEY"

compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

if [[ "${ROLLBACK}" == "1" && -z "${TAG}" ]]; then
  if [[ ! -f "${STATE_DIR}/previous_tag" ]]; then
    echo "ERROR: no previous_tag recorded on this VM (cannot rollback)." >&2
    exit 1
  fi
  TAG="$(cat "${STATE_DIR}/previous_tag" | tr -d '\n' || true)"
  if [[ -z "${TAG}" ]]; then
    echo "ERROR: previous_tag file is empty (cannot rollback)." >&2
    exit 1
  fi
  echo "deploy: rollback -> ${TAG}"
fi

if [[ -z "${TAG}" ]]; then
  echo "ERROR: --tag is required" >&2
  usage >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  echo "deploy: cloning repo"
  rm -rf "${REPO_DIR:?}/"*
  git clone "${REPO_URL}" "${REPO_DIR}"
fi

cd "${REPO_DIR}"

echo "deploy: fetch tags"
git fetch --tags --prune

if ! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "ERROR: tag not found on remote: ${TAG}" >&2
  exit 1
fi

CURRENT_TAG=""
if [[ -f "${STATE_DIR}/current_tag" ]]; then
  CURRENT_TAG="$(cat "${STATE_DIR}/current_tag" | tr -d '\n' || true)"
fi

echo "deploy: checkout ${TAG}"
git checkout -f "tags/${TAG}" >/dev/null

# Symlink secrets into the repo root (docker compose reads .env in project directory).
rm -f .env
ln -s "${ENV_DST}" .env

echo "deploy: docker compose up"
COMPOSE_ARGS=(-f docker-compose.yml)
if [[ "${ENABLE_CADDY}" == "1" ]]; then
  COMPOSE_ARGS+=(-f infra/gcp/docker-compose.caddy.yml)
fi
compose "${COMPOSE_ARGS[@]}" up -d --build

echo "deploy: healthcheck"
bash infra/gcp/healthcheck.sh

if [[ -n "${CURRENT_TAG}" && "${CURRENT_TAG}" != "${TAG}" ]]; then
  echo "${CURRENT_TAG}" > "${STATE_DIR}/previous_tag"
fi
echo "${TAG}" > "${STATE_DIR}/current_tag"

echo "ok: deployed ${TAG}"

