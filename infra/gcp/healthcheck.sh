#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUNNER_URL="${RUNNER_URL:-http://localhost:8000}"
N8N_URL="${N8N_URL:-http://localhost:5678}"

compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

echo "health: docker"
compose ps

echo "health: runner /health"
curl -fsS "${RUNNER_URL}/health" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="healthy"'

echo "health: runner /api/report/daily"
curl -fsS "${RUNNER_URL}/api/report/daily" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="success"'

echo "health: n8n port"
code="$(curl -sS -o /dev/null -w '%{http_code}' "${N8N_URL}/" || true)"
case "$code" in
  200|301|302|401) echo "ok: n8n http ${code}" ;;
  *) echo "ERROR: n8n not reachable (http ${code})" >&2; exit 1 ;;
esac

echo "OK"

