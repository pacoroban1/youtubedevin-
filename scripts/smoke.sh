#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found (install Docker Engine or Docker Desktop)." >&2
  exit 1
fi

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  echo "ERROR: Docker Compose not found (need docker-compose or docker compose)." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running (cannot connect to Docker)." >&2
  echo "Start Docker Desktop, then re-run: make smoke" >&2
  exit 1
fi

RUNNER_URL="${RUNNER_URL:-http://localhost:8000}"

echo "[1/5] Starting main stack (runner/n8n/postgres)..."
"${COMPOSE_CMD[@]}" up -d --build

echo "[2/5] Waiting for runner health at ${RUNNER_URL}/health ..."
for i in $(seq 1 60); do
  if curl -fsS "${RUNNER_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "${RUNNER_URL}/health" | python3 -m json.tool

echo "[3/5] Runner Gemini voice verification gate..."
VOICE_TMP="$(mktemp -t voice_verify.XXXXXX.json)"
curl -fsS "${RUNNER_URL}/api/verify/voice" > "${VOICE_TMP}"

python3 - "${VOICE_TMP}" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, "r", encoding="utf-8"))
ok = data.get("status") == "success" and bool(data.get("gemini_configured"))
if not ok:
  raise SystemExit(f"ERROR: Gemini voice verify failed: {data}")
print("OK: Gemini TTS configured")
PY

echo "[4/5] Runner config summary (non-secret)..."
CONF_TMP="$(mktemp -t runner_config.XXXXXX.json)"
curl -fsS "${RUNNER_URL}/api/config" > "${CONF_TMP}"
python3 - "${CONF_TMP}" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
yt = data.get("youtube") or {}
api_ok = bool(yt.get("api_key_configured"))
oauth_ok = bool(yt.get("oauth_configured"))
print("YouTube API key configured:", api_ok)
print("YouTube OAuth configured:", oauth_ok)
if not api_ok or not oauth_ok:
  print("WARN: Full autopilot (discover + upload) requires YOUTUBE_API_KEY + OAuth creds in .env")
PY

echo "[extra] 10-second ffmpeg encode inside runner container..."
"${COMPOSE_CMD[@]}" exec -T runner bash -lc 'set -euo pipefail; rm -f /tmp/smoke.mp4; ffmpeg -hide_banner -y -f lavfi -i testsrc=size=1280x720:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 10 -pix_fmt yuv420p -c:v libx264 -preset veryfast -crf 28 -c:a aac /tmp/smoke.mp4 >/dev/null; ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 /tmp/smoke.mp4'

echo "SMOKE OK"
