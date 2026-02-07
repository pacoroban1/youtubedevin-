#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[finetune_z] repo: $ROOT_DIR"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: No NVIDIA GPU detected (nvidia-smi not found)." >&2
  echo "This target is GPU-only. Use a cloud GPU box (RunPod/Vast) or your Linux GPU machine." >&2
  echo "Cloud helper: scripts/cloud/runpod_train.sh" >&2
  exit 2
fi

GPU_INFO="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null || true)"
if [ -z "$GPU_INFO" ]; then
  echo "ERROR: nvidia-smi failed. Is the NVIDIA driver working?" >&2
  exit 2
fi

GPU_NAME="$(echo "$GPU_INFO" | head -n1 | cut -d',' -f1 | xargs)"
VRAM_MB="$(echo "$GPU_INFO" | head -n1 | cut -d',' -f2 | xargs)"
VRAM_MB="${VRAM_MB:-0}"

echo "[finetune_z] GPU: $GPU_NAME (${VRAM_MB} MB)"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found. Install Docker Engine and retry." >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running." >&2
  exit 2
fi

# Verify that Docker can actually see the GPU (common failure on fresh cloud boxes).
if ! docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: Docker cannot access the NVIDIA GPU (docker --gpus all failed)." >&2
  echo "Install/configure NVIDIA Container Toolkit (nvidia-container-runtime), then retry." >&2
  exit 2
fi

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  echo "ERROR: Docker Compose not found (need docker-compose or docker compose)." >&2
  exit 2
fi

PRESET="${PRESET:-fast}"
STYLE_TAG="${STYLE_TAG:-alien_reveal}"
DATASET_MODE="${DATASET_MODE:-manual}"   # manual|bootstrap
IMPORT_DIR="${IMPORT_DIR:-}"            # required for bootstrap
AUTO_CAPTION="${AUTO_CAPTION:-false}"   # bootstrap only
CAPTION_MODEL="${CAPTION_MODEL:-Salesforce/blip-image-captioning-base}"

# Training params (overridable)
LR="${LR:-1e-4}"
TIER="${TIER:-}"
RANK="${RANK:-}"
STEPS="${STEPS:-}"

case "$PRESET" in
  fast)
    RANK="${RANK:-8}"
    STEPS="${STEPS:-800}"
    ;;
  quality)
    RANK="${RANK:-16}"
    STEPS="${STEPS:-2500}"
    ;;
  *)
    echo "ERROR: Unknown PRESET=$PRESET (use fast|quality)" >&2
    exit 2
    ;;
esac

if [ -z "$TIER" ]; then
  if [ "$VRAM_MB" -ge 24000 ]; then
    TIER="24gb"
  elif [ "$VRAM_MB" -ge 16000 ]; then
    TIER="16gb"
  elif [ "$VRAM_MB" -ge 12000 ]; then
    TIER="12gb"
  else
    TIER="8gb"
  fi
fi

RUN_NAME="${RUN_NAME:-zthumb_${PRESET}_$(date -u +%Y-%m-%d_%H%M%S)}"
TRAIN_OUT="outputs/lora/${RUN_NAME}"
EXPORT_OUT="models/lora/${RUN_NAME}"
EVAL_OUT="outputs/lora_eval/${RUN_NAME}"
STATE_DIR="outputs/finetune_z"

mkdir -p "outputs/lora" "outputs/lora_eval" "models/lora" "$STATE_DIR"

echo "[finetune_z] preset=$PRESET tier=$TIER steps=$STEPS rank=$RANK lr=$LR run=$RUN_NAME"

echo "[1/5] Downloading base model (SDXL base) with SHA verification..."
python3 zthumb/scripts/download_models.py --variant full --models-dir models

echo "[2/5] Building training container image (pinned deps)..."
docker build -t zthumb-training:cuda -f training/Dockerfile.cuda training

GPU_ARGS=(--gpus all)

echo "[3/5] Preparing dataset (${DATASET_MODE})..."
PREP_CMD=(/workspace/prepare_dataset.py --dataset datasets/thumbs --mode "$DATASET_MODE" --style-tag "$STYLE_TAG")
if [ "$DATASET_MODE" = "manual" ]; then
  # Allow push-button runs: fill missing captions with skeletons instead of crashing.
  PREP_CMD+=(--allow-missing-captions)
elif [ "$DATASET_MODE" = "bootstrap" ]; then
  if [ -z "$IMPORT_DIR" ]; then
    echo "ERROR: DATASET_MODE=bootstrap requires IMPORT_DIR=/path/to/images" >&2
    exit 2
  fi
  PREP_CMD+=(--import-dir "$IMPORT_DIR")
  if [ "$AUTO_CAPTION" = "true" ]; then
    PREP_CMD+=(--auto-caption --caption-model "$CAPTION_MODEL")
  fi
else
  echo "ERROR: unknown DATASET_MODE=$DATASET_MODE" >&2
  exit 2
fi

docker run --rm \
  "${GPU_ARGS[@]}" \
  -v "$ROOT_DIR:/repo" \
  -w /repo \
  zthumb-training:cuda \
  "${PREP_CMD[@]}"

echo "[4/5] Training LoRA..."
TRAIN_CMD=(/workspace/train_lora.py
  --dataset datasets/thumbs
  --output "$TRAIN_OUT"
  --tier "$TIER"
  --steps "$STEPS"
  --lr "$LR"
  --rank "$RANK"
)

HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface}"
HF_MOUNT=()
if [ -d "$HF_CACHE" ]; then
  HF_MOUNT+=(-v "$HF_CACHE:/root/.cache/huggingface")
fi

docker run --rm \
  "${GPU_ARGS[@]}" \
  -v "$ROOT_DIR:/repo" \
  "${HF_MOUNT[@]}" \
  -w /repo \
  zthumb-training:cuda \
  "${TRAIN_CMD[@]}"

echo "[export] Copying adapter weights into $EXPORT_OUT ..."
mkdir -p "$EXPORT_OUT"

WEIGHTS=""
if [ -f "$TRAIN_OUT/pytorch_lora_weights.safetensors" ]; then
  WEIGHTS="$TRAIN_OUT/pytorch_lora_weights.safetensors"
elif [ -f "$TRAIN_OUT/pytorch_lora_weights.bin" ]; then
  WEIGHTS="$TRAIN_OUT/pytorch_lora_weights.bin"
fi

if [ -z "$WEIGHTS" ]; then
  echo "ERROR: No LoRA weights found in $TRAIN_OUT (expected pytorch_lora_weights.safetensors)" >&2
  exit 2
fi

cp -f "$WEIGHTS" "$EXPORT_OUT/$(basename "$WEIGHTS")"
if [ -f "$TRAIN_OUT/adapter_config.json" ]; then
  cp -f "$TRAIN_OUT/adapter_config.json" "$EXPORT_OUT/adapter_config.json"
fi
if [ -f "$TRAIN_OUT/training_meta.json" ]; then
  cp -f "$TRAIN_OUT/training_meta.json" "$EXPORT_OUT/training_meta.json"
fi

cat > "$EXPORT_OUT/README.txt" <<EOF
ZThumb LoRA Adapter

Run name: $RUN_NAME
Created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Preset: $PRESET
Tier: $TIER
Steps: $STEPS
Rank: $RANK
LR: $LR

To use in ZThumb:
  export Z_LORA_PATH=/models/lora/$RUN_NAME
  export Z_LORA_SCALE=0.8
EOF

echo "[5/5] Validating via ZThumb API + writing report..."

echo "  Ensuring ZThumb server is up on http://localhost:8100 ..."
(cd zthumb && "${COMPOSE_CMD[@]}" up -d --build)

for i in $(seq 1 60); do
  if curl -fsS "http://localhost:8100/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://localhost:8100/health" | python3 -m json.tool >/dev/null || true

docker run --rm \
  "${GPU_ARGS[@]}" \
  --network host \
  -v "$ROOT_DIR:/repo" \
  -w /repo \
  zthumb-training:cuda \
  /repo/scripts/eval_lora_report.py \
    --zthumb-url "http://127.0.0.1:8100" \
    --variant full \
    --lora-path "/models/lora/${RUN_NAME}" \
    --out "$EVAL_OUT"

cat > "$STATE_DIR/last_run.json" <<EOF
{
  "run_name": "$(printf '%s' "$RUN_NAME")",
  "train_out": "$(printf '%s' "$TRAIN_OUT")",
  "export_out": "$(printf '%s' "$EXPORT_OUT")",
  "eval_out": "$(printf '%s' "$EVAL_OUT")"
}
EOF

echo ""
echo "OK: LoRA adapter exported to: $EXPORT_OUT"
echo "OK: Eval report: $EVAL_OUT/report.md"
echo ""
echo "Next (inference):"
echo "  cd zthumb"
echo "  export Z_LORA_PATH=/models/lora/$RUN_NAME"
echo "  export Z_LORA_SCALE=0.8"
echo "  ./run_zthumb.sh"
