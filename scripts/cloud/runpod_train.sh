#!/usr/bin/env bash
set -euo pipefail

# Cloud GPU training runner (RunPod/Vast/etc).
#
# Intent: run this ON the cloud GPU box (Ubuntu VM) after you SSH in.
# It will:
#  1) clone the repo (or reuse an existing checkout)
#  2) run `make finetune_z` (GPU-only)
#  3) package the exported adapter under models/lora/<run_name>
#  4) upload the artifact via rclone / gsutil / scp
#
# Required env (choose ONE upload method):
#   REPO_URL=...                          # git clone URL
#   PRESET=fast|quality                   # default: quality
#   UPLOAD_METHOD=rclone|gsutil|scp
#   RCLONE_DEST=remote:bucket/path        # if UPLOAD_METHOD=rclone
#   GSUTIL_DEST=gs://bucket/path          # if UPLOAD_METHOD=gsutil
#   SCP_DEST=user@host:/path              # if UPLOAD_METHOD=scp
#
# Optional env:
#   REPO_REF=...                          # git ref (branch/tag/sha)
#   WORKDIR=...                           # default: ~/zthumb-train
#   RUN_NAME=...                          # forwarded into finetune_z
#   DATASET_MODE=manual|bootstrap
#   IMPORT_DIR=/path/to/images            # for bootstrap
#   AUTO_CAPTION=true|false
#   STYLE_TAG=alien_reveal|doorway_silhouette|split_transformation

REPO_URL="${REPO_URL:-}"
REPO_REF="${REPO_REF:-}"
WORKDIR="${WORKDIR:-$HOME/zthumb-train}"
PRESET="${PRESET:-quality}"
UPLOAD_METHOD="${UPLOAD_METHOD:-}"
RCLONE_DEST="${RCLONE_DEST:-}"
GSUTIL_DEST="${GSUTIL_DEST:-}"
SCP_DEST="${SCP_DEST:-}"

if [ -z "$REPO_URL" ]; then
  echo "ERROR: missing REPO_URL (git clone URL)" >&2
  exit 2
fi
if [ -z "$UPLOAD_METHOD" ]; then
  echo "ERROR: missing UPLOAD_METHOD=rclone|gsutil|scp" >&2
  exit 2
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. This machine does not look like a GPU box." >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. Install Docker Engine on this box and retry." >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: docker daemon not running." >&2
  exit 2
fi

mkdir -p "$WORKDIR"
cd "$WORKDIR"

if [ ! -d repo/.git ]; then
  echo "[cloud] cloning repo..."
  git clone "$REPO_URL" repo
fi

cd repo
git fetch --all --tags -q || true
if [ -n "$REPO_REF" ]; then
  echo "[cloud] checking out REPO_REF=$REPO_REF"
  git checkout -q "$REPO_REF"
fi

echo "[cloud] running finetune pipeline..."
PRESET="$PRESET" \
DATASET_MODE="${DATASET_MODE:-manual}" \
IMPORT_DIR="${IMPORT_DIR:-}" \
AUTO_CAPTION="${AUTO_CAPTION:-false}" \
STYLE_TAG="${STYLE_TAG:-alien_reveal}" \
RUN_NAME="${RUN_NAME:-}" \
make finetune_z

STATE_FILE="outputs/finetune_z/last_run.json"
if [ ! -f "$STATE_FILE" ]; then
  echo "ERROR: expected state file missing: $STATE_FILE" >&2
  exit 2
fi

RUN_NAME_DETECTED="$(python3 -c 'import json;print(json.load(open("outputs/finetune_z/last_run.json"))["run_name"])')"
EXPORT_OUT="$(python3 -c 'import json;print(json.load(open("outputs/finetune_z/last_run.json"))["export_out"])')"

if [ ! -d "$EXPORT_OUT" ]; then
  echo "ERROR: export_out directory missing: $EXPORT_OUT" >&2
  exit 2
fi

ART_DIR="outputs/finetune_z/artifacts"
mkdir -p "$ART_DIR"
TARBALL="$ART_DIR/${RUN_NAME_DETECTED}.tar.gz"
echo "[cloud] packaging adapter: $TARBALL"
tar -czf "$TARBALL" -C "$(dirname "$EXPORT_OUT")" "$(basename "$EXPORT_OUT")"

case "$UPLOAD_METHOD" in
  rclone)
    if [ -z "$RCLONE_DEST" ]; then
      echo "ERROR: UPLOAD_METHOD=rclone requires RCLONE_DEST" >&2
      exit 2
    fi
    if ! command -v rclone >/dev/null 2>&1; then
      echo "ERROR: rclone not found. Install it on this box and retry." >&2
      exit 2
    fi
    echo "[cloud] uploading via rclone -> $RCLONE_DEST"
    rclone copy "$TARBALL" "$RCLONE_DEST"
    ;;
  gsutil)
    if [ -z "$GSUTIL_DEST" ]; then
      echo "ERROR: UPLOAD_METHOD=gsutil requires GSUTIL_DEST" >&2
      exit 2
    fi
    if ! command -v gsutil >/dev/null 2>&1; then
      echo "ERROR: gsutil not found. Install Google Cloud SDK and retry." >&2
      exit 2
    fi
    echo "[cloud] uploading via gsutil -> $GSUTIL_DEST"
    gsutil cp "$TARBALL" "$GSUTIL_DEST/"
    ;;
  scp)
    if [ -z "$SCP_DEST" ]; then
      echo "ERROR: UPLOAD_METHOD=scp requires SCP_DEST" >&2
      exit 2
    fi
    if ! command -v scp >/dev/null 2>&1; then
      echo "ERROR: scp not found." >&2
      exit 2
    fi
    echo "[cloud] uploading via scp -> $SCP_DEST"
    scp "$TARBALL" "$SCP_DEST"
    ;;
  *)
    echo "ERROR: unknown UPLOAD_METHOD=$UPLOAD_METHOD (use rclone|gsutil|scp)" >&2
    exit 2
    ;;
esac

echo ""
echo "OK: uploaded LoRA artifact:"
echo "  run_name=$RUN_NAME_DETECTED"
echo "  tarball=$TARBALL"

