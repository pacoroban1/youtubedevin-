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

ZTHUMB_URL="${ZTHUMB_URL:-http://localhost:8100}"
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

echo "[3/5] Ensuring ZThumb is running at ${ZTHUMB_URL} ..."
if ! curl -fsS "${ZTHUMB_URL}/health" >/dev/null 2>&1; then
  echo "ZThumb not healthy yet; starting via ./zthumb/run_zthumb.sh"
  (cd zthumb && ./run_zthumb.sh)
fi
curl -fsS "${ZTHUMB_URL}/health" | python3 -m json.tool

echo "[4/5] ZThumb generate test (1 image)..."
GEN_TMP="$(mktemp -t zthumb_gen.XXXXXX.json)"
curl -fsS -X POST "${ZTHUMB_URL}/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cinematic alien creature reveal, ultra high contrast, thumbnail composition","batch":1,"style_preset":"alien_reveal"}' \
  > "${GEN_TMP}"

python3 - "${GEN_TMP}" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, "r", encoding="utf-8"))
imgs = data.get("images") or []
warn = data.get("warnings") or []
if warn:
  print("WARN: ZThumb warnings:", warn)
if not imgs:
  print("ERROR: ZThumb returned no images")
  sys.exit(1)
print("OK: ZThumb returned", len(imgs), "image(s)")
print("First:", imgs[0])
PY

echo "[5/5] Runner voice verification gate..."
VOICE_TMP="$(mktemp -t voice_verify.XXXXXX.json)"
curl -fsS "${RUNNER_URL}/api/verify/voice" > "${VOICE_TMP}"

python3 - "${VOICE_TMP}" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, "r", encoding="utf-8"))
v = (data.get("verification") or {}).get("azure_tts") or {}
supported = bool(v.get("supported"))
test = bool(v.get("test_synthesis"))
voices = v.get("voices") or []
if not supported and not voices:
  print("ERROR: Azure TTS did not report am-ET support. Details:", v)
  sys.exit(1)
if not test:
  print("ERROR: Azure TTS test synthesis failed. Details:", v)
  sys.exit(1)
print("OK: Azure TTS supports am-ET. Voices:", voices[:5])
PY

echo "[extra] 10-second ffmpeg encode inside runner container..."
"${COMPOSE_CMD[@]}" exec -T runner bash -lc 'set -euo pipefail; rm -f /tmp/smoke.mp4; ffmpeg -hide_banner -y -f lavfi -i testsrc=size=1280x720:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 10 -pix_fmt yuv420p -c:v libx264 -preset veryfast -crf 28 -c:a aac /tmp/smoke.mp4 >/dev/null; ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 /tmp/smoke.mp4'

echo "SMOKE OK"
