#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found (install Docker Engine or Docker Desktop)." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running." >&2
  exit 1
fi

TRAIN_DEVICE="${TRAIN_DEVICE:-}"
if [ -z "$TRAIN_DEVICE" ]; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    TRAIN_DEVICE="cuda"
  else
    TRAIN_DEVICE="cpu"
  fi
fi

IMG_TAG="zthumb-training:${TRAIN_DEVICE}"
DOCKERFILE="training/Dockerfile.${TRAIN_DEVICE}"
if ! docker image inspect "$IMG_TAG" >/dev/null 2>&1; then
  echo "[build] $IMG_TAG ($DOCKERFILE)"
  docker build -t "$IMG_TAG" -f "$DOCKERFILE" training
fi

GPU_ARGS=()
if [ "$TRAIN_DEVICE" = "cuda" ]; then
  GPU_ARGS+=(--gpus all)
fi

LORA="${LORA:-outputs/lora/zthumb_lora}"
OUT="${OUT:-outputs/eval}"
BASE_MODEL="${BASE_MODEL:-}"

CMD=(/workspace/eval_lora.py --lora "$LORA" --out "$OUT")
if [ -n "$BASE_MODEL" ]; then
  CMD+=(--base-model "$BASE_MODEL")
fi

echo "[run] eval LoRA (device=$TRAIN_DEVICE lora=$LORA)"
docker run --rm \
  "${GPU_ARGS[@]}" \
  -v "$ROOT_DIR:/repo" \
  -w /repo \
  "$IMG_TAG" \
  "${CMD[@]}"
