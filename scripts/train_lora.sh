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
if [ ! -f "$DOCKERFILE" ]; then
  echo "ERROR: missing Dockerfile: $DOCKERFILE" >&2
  exit 1
fi

echo "[build] $IMG_TAG ($DOCKERFILE)"
docker build -t "$IMG_TAG" -f "$DOCKERFILE" training

GPU_ARGS=()
if [ "$TRAIN_DEVICE" = "cuda" ]; then
  GPU_ARGS+=(--gpus all)
fi

TIER="${TIER:-12gb}"
STEPS="${STEPS:-1500}"
LR="${LR:-1e-4}"
RANK="${RANK:-16}"
OUTPUT="${OUTPUT:-outputs/lora/zthumb_lora}"
BASE_MODEL="${BASE_MODEL:-}"

HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface}"
HF_MOUNT=()
if [ -d "$HF_CACHE" ]; then
  HF_MOUNT+=(-v "$HF_CACHE:/root/.cache/huggingface")
fi

CMD=(/workspace/train_lora.py
  --dataset datasets/thumbs
  --output "$OUTPUT"
  --tier "$TIER"
  --steps "$STEPS"
  --lr "$LR"
  --rank "$RANK"
)
if [ -n "$BASE_MODEL" ]; then
  CMD+=(--base-model "$BASE_MODEL")
fi

echo "[run] training LoRA (device=$TRAIN_DEVICE tier=$TIER steps=$STEPS)"
docker run --rm \
  "${GPU_ARGS[@]}" \
  -v "$ROOT_DIR:/repo" \
  "${HF_MOUNT[@]}" \
  -w /repo \
  "$IMG_TAG" \
  "${CMD[@]}"

echo "OK: LoRA output at $OUTPUT"
echo "Set for ZThumb:"
echo "  export Z_LORA_PATH=/outputs/lora/$(basename "$OUTPUT")"
echo "  export Z_LORA_SCALE=0.8"
