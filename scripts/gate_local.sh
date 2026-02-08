#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNNER_URL="${RUNNER_URL:-http://localhost:8000}"
VIDEO_ID="${VIDEO_ID:-${TEST_VIDEO_ID:-}}"
REQUIRE_PIPELINE="${REQUIRE_PIPELINE:-0}"

export VIDEO_ID

_tmp_dir="$(mktemp -d)"
cleanup() { rm -rf "${_tmp_dir}"; }
trap cleanup EXIT

fail() {
  echo "LOCAL GATE FAILED"
  exit 1
}

run_step() {
  local name="$1"
  shift

  local log="${_tmp_dir}/${name}.log"
  : >"$log"

  echo "gate: ${name}"
  if ! "$@" >"$log" 2>&1; then
    echo "fail: ${name}"
    echo "---- ${name} (tail) ----"
    tail -n 200 "$log" || true
    echo "------------------------"
    fail
  fi
  echo "ok: ${name}"
}

run_step "verify" make verify
run_step "doctor" make doctor
run_step "smoke" make smoke

run_step "runner_health" bash -lc "curl -fsS \"${RUNNER_URL}/health\" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get(\"status\")==\"healthy\"'"

if [[ "${REQUIRE_PIPELINE}" == "1" && -z "${VIDEO_ID}" ]]; then
  echo "fail: pipeline (VIDEO_ID required)"
  fail
fi

if [[ -n "${VIDEO_ID}" ]]; then
  # Avoid echoing request payloads (may contain ids). Only surface on failure.
  run_step "pipeline_full" bash -lc "\
    body=\$(python3 - <<'PY'\nimport json, os\nprint(json.dumps({\"video_id\": os.environ.get(\"VIDEO_ID\"), \"auto_select\": False}))\nPY\n    ); \
    code=\$(curl -sS -o \"${_tmp_dir}/pipeline.json\" -w '%{http_code}' -X POST \"${RUNNER_URL}/api/pipeline/full\" -H 'Content-Type: application/json' -d \"\$body\" || true); \
    test \"\$code\" = \"200\"; \
    python3 - <<'PY'\nimport json\ndata = json.load(open(\"${_tmp_dir}/pipeline.json\", \"r\", encoding=\"utf-8\"))\nassert data.get(\"status\") == \"success\", data\nPY"
fi

echo "LOCAL GATE PASSED"
