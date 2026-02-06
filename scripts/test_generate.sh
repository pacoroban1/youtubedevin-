#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ZTHUMB_URL="${ZTHUMB_URL:-http://localhost:8100}"
STYLE_PRESET="${STYLE_PRESET:-alien_reveal}"
LORA_SCALE="${LORA_SCALE:-0.8}"

OUT_DIR="$ROOT_DIR/outputs/test_generate/$(date +%Y-%m-%d_%H%M%S)"
mkdir -p "$OUT_DIR"

REQ_TMP="$(mktemp -t zthumb_req.XXXXXX.json)"
RESP_TMP="$(mktemp -t zthumb_resp.XXXXXX.json)"

cat >"$REQ_TMP" <<JSON
{
  "prompt": "cinematic creature reveal, dramatic lighting, high contrast, mobile-readable composition",
  "batch": 4,
  "style_preset": "${STYLE_PRESET}",
  "lora_scale": ${LORA_SCALE}
}
JSON

curl -fsS -X POST "${ZTHUMB_URL}/generate" \
  -H "Content-Type: application/json" \
  -d @"$REQ_TMP" > "$RESP_TMP"

python3 - "$RESP_TMP" "$ROOT_DIR" "$OUT_DIR" <<'PY'
import json, os, shutil, sys

resp_path, root_dir, out_dir = sys.argv[1:4]
data = json.load(open(resp_path, "r", encoding="utf-8"))
imgs = data.get("images") or []
if not imgs:
  raise SystemExit(f"ERROR: no images returned. warnings={data.get('warnings')}")

copied = []
for i, uri in enumerate(imgs):
  p = uri.replace("file://", "")
  if p.startswith("/outputs/"):
    host_path = os.path.join(root_dir, "outputs", p[len("/outputs/"):])
  else:
    host_path = p
  if not os.path.exists(host_path):
    raise SystemExit(f"ERROR: expected generated file on host not found: {host_path}")
  dst = os.path.join(out_dir, f"img_{i+1}.png")
  shutil.copy2(host_path, dst)
  copied.append(dst)

print("OK: copied images:")
for c in copied:
  print(" -", c)
PY

echo "OK: Response JSON saved at: $RESP_TMP"

